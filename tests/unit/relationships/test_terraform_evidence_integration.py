"""Tests for terraform_evidence integration with the main evidence pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from platform_context_graph.relationships.file_evidence_support import CatalogEntry
from platform_context_graph.relationships.models import RepositoryCheckout


@pytest.fixture()
def sample_checkout() -> RepositoryCheckout:
    """Return a minimal checkout for testing."""
    return RepositoryCheckout(
        checkout_id="checkout:test_infra",
        logical_repo_id="repository:r_infra",
        repo_name="terraform-stack-test",
        repo_slug="org/terraform-stack-test",
        remote_url="https://github.com/org/terraform-stack-test",
        checkout_path="/tmp/nonexistent-path",
    )


@pytest.fixture()
def sample_catalog() -> list[CatalogEntry]:
    """Return a catalog with test repos."""
    return [
        CatalogEntry(
            repo_id="repository:r_boats",
            repo_name="api-node-boats",
            aliases=("api-node-boats",),
        ),
        CatalogEntry(
            repo_id="repository:r_lambda",
            repo_name="my-lambda-func",
            aliases=("my-lambda-func",),
        ),
    ]


class TestDiscoverTerraformEvidenceIncludesResourceEvidence:
    """Verify that discover_terraform_evidence delegates to the resource registry."""

    def test_lambda_function_produces_evidence_via_registry(
        self,
        sample_checkout: RepositoryCheckout,
        sample_catalog: list[CatalogEntry],
    ) -> None:
        """A Lambda function with function_name matching a catalog entry
        should produce PROVISIONS_DEPENDENCY_FOR evidence through the
        registry-based extractor, not just the legacy pattern matcher."""
        from platform_context_graph.relationships.evidence_terraform import (
            discover_terraform_evidence,
        )

        # Content with a Lambda function — no legacy pattern match (no app_repo,
        # no GitHub URL), but the registry extractor should pick it up.
        checkouts = [sample_checkout]
        catalog = [
            CatalogEntry(
                repo_id="repository:r_lambda",
                repo_name="my-lambda-func",
                aliases=("my-lambda-func",),
            ),
        ]

        # Mock the content store to return this terraform content
        tf_content = """
resource "aws_lambda_function" "handler" {
  function_name = "my-lambda-func"
  runtime       = "python3.12"
  handler       = "index.handler"
}
"""
        # We need to patch iter_terraform_files_from_content_store to return our content
        import platform_context_graph.relationships.evidence_terraform as mod

        original_fn = mod.iter_terraform_files_from_content_store

        def mock_content_store(checkout: RepositoryCheckout) -> list:
            return [(Path("/tmp/main.tf"), tf_content)]

        mod.iter_terraform_files_from_content_store = mock_content_store
        try:
            evidence = discover_terraform_evidence(checkouts, catalog)
        finally:
            mod.iter_terraform_files_from_content_store = original_fn

        # Should find TERRAFORM_LAMBDA_FUNCTION evidence from the registry
        lambda_evidence = [
            e for e in evidence if e.evidence_kind == "TERRAFORM_LAMBDA_FUNCTION"
        ]
        assert len(lambda_evidence) >= 1
        assert lambda_evidence[0].relationship_type == "PROVISIONS_DEPENDENCY_FOR"
        assert lambda_evidence[0].target_repo_id == "repository:r_lambda"

    def test_ecs_service_produces_evidence_via_registry(
        self,
        sample_checkout: RepositoryCheckout,
        sample_catalog: list[CatalogEntry],
    ) -> None:
        """An ECS service with name matching a catalog entry should produce
        evidence through the registry extractor."""
        from platform_context_graph.relationships.evidence_terraform import (
            discover_terraform_evidence,
        )

        import platform_context_graph.relationships.evidence_terraform as mod

        original_fn = mod.iter_terraform_files_from_content_store

        def mock_content_store(checkout: RepositoryCheckout) -> list:
            return [
                (
                    Path("/tmp/ecs.tf"),
                    """
resource "aws_ecs_service" "boats" {
  name = "api-node-boats"
}
""",
                )
            ]

        mod.iter_terraform_files_from_content_store = mock_content_store
        try:
            evidence = discover_terraform_evidence([sample_checkout], sample_catalog)
        finally:
            mod.iter_terraform_files_from_content_store = original_fn

        ecs_evidence = [
            e for e in evidence if e.evidence_kind == "TERRAFORM_ECS_SERVICE"
        ]
        assert len(ecs_evidence) >= 1
        assert ecs_evidence[0].target_repo_id == "repository:r_boats"

    def test_ecr_repository_produces_evidence_via_registry(
        self,
        sample_checkout: RepositoryCheckout,
        sample_catalog: list[CatalogEntry],
    ) -> None:
        """An ECR repo name matching a catalog entry should produce evidence."""
        from platform_context_graph.relationships.evidence_terraform import (
            discover_terraform_evidence,
        )

        import platform_context_graph.relationships.evidence_terraform as mod

        original_fn = mod.iter_terraform_files_from_content_store

        def mock_content_store(checkout: RepositoryCheckout) -> list:
            return [
                (
                    Path("/tmp/ecr.tf"),
                    """
resource "aws_ecr_repository" "boats" {
  name = "api-node-boats"
}
""",
                )
            ]

        mod.iter_terraform_files_from_content_store = mock_content_store
        try:
            evidence = discover_terraform_evidence([sample_checkout], sample_catalog)
        finally:
            mod.iter_terraform_files_from_content_store = original_fn

        ecr_evidence = [
            e for e in evidence if e.evidence_kind == "TERRAFORM_ECR_REPOSITORY"
        ]
        assert len(ecr_evidence) >= 1
        assert ecr_evidence[0].target_repo_id == "repository:r_boats"

    def test_legacy_patterns_still_work(
        self,
        sample_checkout: RepositoryCheckout,
        sample_catalog: list[CatalogEntry],
    ) -> None:
        """Existing _TERRAFORM_PATTERNS (app_repo, GitHub URLs, etc.)
        should still produce evidence alongside the registry."""
        from platform_context_graph.relationships.evidence_terraform import (
            discover_terraform_evidence,
        )

        import platform_context_graph.relationships.evidence_terraform as mod

        original_fn = mod.iter_terraform_files_from_content_store

        def mock_content_store(checkout: RepositoryCheckout) -> list:
            return [
                (
                    Path("/tmp/legacy.tf"),
                    """
# Legacy pattern: app_repo
data "aws_iam_policy_document" "boats" {
  statement {
    resources = [
      "arn:aws:ssm:us-east-1:123456:parameter/configd/api-node-boats/*"
    ]
  }
}
""",
                )
            ]

        mod.iter_terraform_files_from_content_store = mock_content_store
        try:
            evidence = discover_terraform_evidence([sample_checkout], sample_catalog)
        finally:
            mod.iter_terraform_files_from_content_store = original_fn

        # The TERRAFORM_CONFIG_PATH pattern should match "/configd/api-node-boats/"
        config_evidence = [
            e for e in evidence if e.evidence_kind == "TERRAFORM_CONFIG_PATH"
        ]
        assert len(config_evidence) >= 1

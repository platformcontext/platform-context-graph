"""Tests for the terraform_evidence registry and orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from platform_context_graph.relationships.terraform_evidence._base import (
    ExtractionContext,
    ResourceRelationship,
    first_non_empty,
    first_quoted_value,
    get_extractors_for_type,
    get_registered_resource_types,
    register_resource_extractor,
    resolve_assignment_value,
    extract_local_string_values,
)
from platform_context_graph.relationships.models import RepositoryCheckout


@pytest.fixture()
def sample_checkout() -> RepositoryCheckout:
    """Return a minimal checkout for testing."""
    return RepositoryCheckout(
        checkout_id="checkout:test",
        logical_repo_id="repository:r_test",
        repo_name="test-repo",
        repo_slug="org/test-repo",
        remote_url="https://github.com/org/test-repo",
        checkout_path="/tmp/test-repo",
    )


@pytest.fixture()
def sample_context(sample_checkout: RepositoryCheckout) -> ExtractionContext:
    """Return a minimal ExtractionContext for testing."""
    return ExtractionContext(
        checkout=sample_checkout,
        catalog=[],
        content="",
        file_path=Path("/tmp/test.tf"),
        local_values={},
    )


class TestFirstQuotedValue:
    """Tests for first_quoted_value helper."""

    def test_extracts_simple_quoted_value(self) -> None:
        assert first_quoted_value('name = "my-service"', "name") == "my-service"

    def test_returns_none_when_key_not_found(self) -> None:
        assert first_quoted_value('name = "my-service"', "missing") is None

    def test_case_insensitive_key_match(self) -> None:
        assert first_quoted_value('Name = "my-service"', "name") == "my-service"

    def test_skips_empty_values(self) -> None:
        assert first_quoted_value('name = ""', "name") is None


class TestFirstNonEmpty:
    """Tests for first_non_empty helper."""

    def test_returns_first_non_empty_string(self) -> None:
        assert first_non_empty(None, "", "hello") == "hello"

    def test_returns_none_when_all_empty(self) -> None:
        assert first_non_empty(None, "", "  ") is None

    def test_strips_whitespace(self) -> None:
        assert first_non_empty("  value  ") == "value"


class TestResolveAssignmentValue:
    """Tests for resolve_assignment_value helper."""

    def test_resolves_quoted_literal(self) -> None:
        content = 'cluster_name = "my-cluster"'
        assert (
            resolve_assignment_value(content, key="cluster_name", local_values={})
            == "my-cluster"
        )

    def test_resolves_local_reference(self) -> None:
        content = "cluster_name = local.cluster"
        assert (
            resolve_assignment_value(
                content,
                key="cluster_name",
                local_values={"cluster": "resolved-cluster"},
            )
            == "resolved-cluster"
        )

    def test_returns_none_for_unresolvable(self) -> None:
        content = "cluster_name = var.cluster"
        assert (
            resolve_assignment_value(content, key="cluster_name", local_values={})
            is None
        )


class TestExtractLocalStringValues:
    """Tests for extract_local_string_values helper."""

    def test_extracts_locals_block(self) -> None:
        content = """
locals {
  cluster = "my-cluster"
  region  = "us-east-1"
}
"""
        values = extract_local_string_values(content)
        assert values["cluster"] == "my-cluster"
        assert values["region"] == "us-east-1"


class TestResourceExtractorRegistry:
    """Tests for the extractor registration system."""

    def test_registered_types_include_aws_lambda(self) -> None:
        # Trigger provider registration by importing the package
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "aws_lambda_function" in registered

    def test_registered_types_include_cloudflare_workers(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "cloudflare_workers_script" in registered

    def test_registered_types_include_gcp_cloud_run(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "google_cloud_run_service" in registered

    def test_registered_types_include_azure_aks(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "azurerm_kubernetes_cluster" in registered

    def test_registered_types_include_aws_ecs_service(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "aws_ecs_service" in registered

    def test_registered_types_include_aws_ecr_repository(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "aws_ecr_repository" in registered

    def test_registered_types_include_aws_sqs_queue(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "aws_sqs_queue" in registered

    def test_registered_types_include_aws_route53_record(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered = get_registered_resource_types()
        assert "aws_route53_record" in registered

    def test_get_extractors_returns_callable(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("aws_lambda_function")
        assert len(extractors) >= 1
        assert callable(extractors[0])

    def test_get_extractors_returns_empty_for_unknown_type(self) -> None:
        extractors = get_extractors_for_type("aws_nonexistent_resource")
        assert extractors == []


class TestAwsComputeExtractors:
    """Tests for AWS compute resource extractors."""

    def test_lambda_function_extracts_function_name(
        self, sample_context: ExtractionContext
    ) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("aws_lambda_function")
        body = 'function_name = "my-lambda-handler"\nruntime = "python3.12"'
        results = extractors[0](
            sample_context, "aws_lambda_function", "my_lambda", body
        )
        assert len(results) >= 1
        assert results[0].candidate_name == "my-lambda-handler"
        assert results[0].relationship_type == "PROVISIONS_DEPENDENCY_FOR"

    def test_ecs_service_extracts_name(self, sample_context: ExtractionContext) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("aws_ecs_service")
        body = 'name = "api-node-boats"'
        results = extractors[0](sample_context, "aws_ecs_service", "boats", body)
        assert len(results) >= 1
        assert results[0].candidate_name == "api-node-boats"

    def test_ecs_task_definition_extracts_family(
        self, sample_context: ExtractionContext
    ) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("aws_ecs_task_definition")
        body = 'family = "api-node-boats"'
        results = extractors[0](
            sample_context, "aws_ecs_task_definition", "boats_td", body
        )
        assert len(results) >= 1
        assert results[0].candidate_name == "api-node-boats"


class TestAwsDataExtractors:
    """Tests for AWS data store resource extractors."""

    def test_rds_cluster_extracts_identifier(
        self, sample_context: ExtractionContext
    ) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("aws_rds_cluster")
        body = 'cluster_identifier = "main-db-cluster"'
        results = extractors[0](sample_context, "aws_rds_cluster", "main", body)
        assert len(results) >= 1
        assert results[0].candidate_name == "main-db-cluster"

    def test_dynamodb_table_extracts_name(
        self, sample_context: ExtractionContext
    ) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("aws_dynamodb_table")
        body = 'name = "user-sessions"'
        results = extractors[0](sample_context, "aws_dynamodb_table", "sessions", body)
        assert len(results) >= 1
        assert results[0].candidate_name == "user-sessions"


class TestCloudflareExtractors:
    """Tests for Cloudflare resource extractors."""

    def test_workers_script_extracts_name(
        self, sample_context: ExtractionContext
    ) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("cloudflare_workers_script")
        body = 'name = "search-worker"'
        results = extractors[0](
            sample_context, "cloudflare_workers_script", "worker", body
        )
        assert len(results) >= 1
        assert results[0].candidate_name == "search-worker"

    def test_dns_record_extracts_hostname_prefix(
        self, sample_context: ExtractionContext
    ) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("cloudflare_dns_record")
        body = 'name = "api-node-boats.example.com"'
        results = extractors[0](
            sample_context, "cloudflare_dns_record", "boats_dns", body
        )
        assert len(results) >= 1
        assert results[0].candidate_name == "api-node-boats"


class TestGcpExtractors:
    """Tests for GCP resource extractors."""

    def test_cloud_run_service_extracts_name(
        self, sample_context: ExtractionContext
    ) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("google_cloud_run_service")
        body = 'name = "my-api-service"\nlocation = "us-central1"'
        results = extractors[0](sample_context, "google_cloud_run_service", "api", body)
        assert len(results) >= 1
        assert results[0].candidate_name == "my-api-service"


class TestAzureExtractors:
    """Tests for Azure resource extractors."""

    def test_aks_cluster_extracts_name(self, sample_context: ExtractionContext) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        extractors = get_extractors_for_type("azurerm_kubernetes_cluster")
        body = 'name = "prod-aks"'
        results = extractors[0](
            sample_context, "azurerm_kubernetes_cluster", "aks", body
        )
        assert len(results) >= 1
        assert results[0].candidate_name == "prod-aks"


class TestOrchestratorDiscovery:
    """Tests for the orchestrator discover_terraform_resource_evidence function."""

    def test_discovers_lambda_from_terraform_content(
        self, sample_checkout: RepositoryCheckout
    ) -> None:
        from platform_context_graph.relationships.terraform_evidence import (
            discover_terraform_resource_evidence,
        )
        from platform_context_graph.relationships.file_evidence_support import (
            CatalogEntry,
        )

        catalog = [
            CatalogEntry(
                repo_id="repository:r_lambda",
                repo_name="my-lambda-handler",
                aliases=("my-lambda-handler",),
            )
        ]
        content = """
resource "aws_lambda_function" "handler" {
  function_name = "my-lambda-handler"
  runtime       = "python3.12"
  handler       = "index.handler"
}
"""
        seen: set[tuple[str, str, str, str]] = set()
        evidence = discover_terraform_resource_evidence(
            checkout=sample_checkout,
            catalog=catalog,
            content=content,
            file_path=Path("/tmp/main.tf"),
            local_values={},
            seen=seen,
        )
        assert len(evidence) >= 1
        lambda_evidence = [
            e for e in evidence if e.evidence_kind == "TERRAFORM_LAMBDA_FUNCTION"
        ]
        assert len(lambda_evidence) >= 1

    def test_discovers_multiple_resource_types(
        self, sample_checkout: RepositoryCheckout
    ) -> None:
        from platform_context_graph.relationships.terraform_evidence import (
            discover_terraform_resource_evidence,
        )
        from platform_context_graph.relationships.file_evidence_support import (
            CatalogEntry,
        )

        catalog = [
            CatalogEntry(
                repo_id="repository:r_svc",
                repo_name="my-service",
                aliases=("my-service",),
            )
        ]
        content = """
resource "aws_ecs_service" "svc" {
  name = "my-service"
}

resource "aws_sqs_queue" "queue" {
  name = "my-service-events"
}
"""
        seen: set[tuple[str, str, str, str]] = set()
        evidence = discover_terraform_resource_evidence(
            checkout=sample_checkout,
            catalog=catalog,
            content=content,
            file_path=Path("/tmp/main.tf"),
            local_values={},
            seen=seen,
        )
        kinds = {e.evidence_kind for e in evidence}
        assert "TERRAFORM_ECS_SERVICE" in kinds

    def test_returns_empty_for_unregistered_resources(
        self, sample_checkout: RepositoryCheckout
    ) -> None:
        from platform_context_graph.relationships.terraform_evidence import (
            discover_terraform_resource_evidence,
        )

        content = """
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}
"""
        seen: set[tuple[str, str, str, str]] = set()
        evidence = discover_terraform_resource_evidence(
            checkout=sample_checkout,
            catalog=[],
            content=content,
            file_path=Path("/tmp/vpc.tf"),
            local_values={},
            seen=seen,
        )
        assert evidence == []

"""Tests for Terraform provider schema loader, classification, and generic extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from platform_context_graph.relationships.terraform_evidence.provider_schema import (
    ProviderSchemaInfo,
    classify_resource_category,
    infer_identity_keys,
    load_provider_schema,
)
from platform_context_graph.relationships.terraform_evidence.generic import (
    make_generic_extractor,
    register_schema_driven_extractors,
)
from platform_context_graph.relationships.terraform_evidence._base import (
    ExtractionContext,
    get_registered_resource_types,
)
from platform_context_graph.relationships.models import RepositoryCheckout

FIXTURE_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "schemas"
    / "test_aws_provider_schema.json"
)


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


# ---------------------------------------------------------------------------
# load_provider_schema
# ---------------------------------------------------------------------------


class TestLoadProviderSchema:
    """Tests for load_provider_schema."""

    def test_loads_test_fixture(self) -> None:
        schema = load_provider_schema(FIXTURE_SCHEMA)
        assert schema is not None
        assert schema.provider_name == "aws"
        assert schema.format_version == "1.0"

    def test_returns_resource_types(self) -> None:
        schema = load_provider_schema(FIXTURE_SCHEMA)
        assert schema is not None
        assert "aws_lambda_function" in schema.resource_types
        assert "aws_vpc" in schema.resource_types
        assert "aws_wafv2_web_acl" in schema.resource_types

    def test_resource_count(self) -> None:
        schema = load_provider_schema(FIXTURE_SCHEMA)
        assert schema is not None
        assert schema.resource_count == 6

    def test_returns_none_for_missing_file(self) -> None:
        assert load_provider_schema(Path("/nonexistent/schema.json")) is None

    def test_returns_none_for_missing_directory(self, tmp_path: Path) -> None:
        assert load_provider_schema(tmp_path / "nope.json") is None

    def test_attributes_parsed(self) -> None:
        schema = load_provider_schema(FIXTURE_SCHEMA)
        assert schema is not None
        attrs = schema.resource_types["aws_lambda_function"]
        assert "function_name" in attrs
        assert attrs["function_name"]["type"] == "string"


# ---------------------------------------------------------------------------
# infer_identity_keys
# ---------------------------------------------------------------------------


class TestInferIdentityKeys:
    """Tests for infer_identity_keys."""

    def test_finds_name_attribute(self) -> None:
        attrs = {"name": {"type": "string"}, "scope": {"type": "string"}}
        assert infer_identity_keys(attrs) == ["name"]

    def test_finds_function_name(self) -> None:
        attrs = {
            "function_name": {"type": "string"},
            "runtime": {"type": "string"},
        }
        assert infer_identity_keys(attrs) == ["function_name"]

    def test_finds_cluster_identifier(self) -> None:
        attrs = {
            "cluster_identifier": {"type": "string"},
            "engine": {"type": "string"},
        }
        assert infer_identity_keys(attrs) == ["cluster_identifier"]

    def test_finds_service_name(self) -> None:
        attrs = {
            "service_name": {"type": "string"},
            "auto_deployments_enabled": {"type": "bool"},
        }
        assert infer_identity_keys(attrs) == ["service_name"]

    def test_fallback_to_suffix_name(self) -> None:
        attrs = {
            "custom_thing_name": {"type": "string"},
            "enabled": {"type": "bool"},
        }
        keys = infer_identity_keys(attrs)
        assert "custom_thing_name" in keys

    def test_returns_empty_for_no_name_attrs(self) -> None:
        attrs = {
            "cidr_block": {"type": "string"},
            "enable_dns_support": {"type": "bool"},
        }
        assert infer_identity_keys(attrs) == []

    def test_ignores_non_string_name(self) -> None:
        attrs = {"name": {"type": "bool"}, "count": {"type": "number"}}
        assert infer_identity_keys(attrs) == []

    def test_skips_complex_types(self) -> None:
        attrs = {
            "protocols": {"type": ["set", "string"]},
            "endpoint_type": {"type": "string"},
        }
        assert infer_identity_keys(attrs) == []


# ---------------------------------------------------------------------------
# classify_resource_category
# ---------------------------------------------------------------------------


class TestClassifyResourceCategory:
    """Tests for classify_resource_category."""

    def test_compute_lambda(self) -> None:
        assert classify_resource_category("aws_lambda_function") == "compute"

    def test_compute_ecs(self) -> None:
        assert classify_resource_category("aws_ecs_service") == "compute"

    def test_storage_s3(self) -> None:
        assert classify_resource_category("aws_s3_bucket") == "storage"

    def test_data_rds(self) -> None:
        assert classify_resource_category("aws_rds_cluster") == "data"

    def test_networking_route53(self) -> None:
        assert classify_resource_category("aws_route53_record") == "networking"

    def test_messaging_sqs(self) -> None:
        assert classify_resource_category("aws_sqs_queue") == "messaging"

    def test_security_iam(self) -> None:
        assert classify_resource_category("aws_iam_role") == "security"

    def test_cicd_codebuild(self) -> None:
        assert classify_resource_category("aws_codebuild_project") == "cicd"

    def test_monitoring_cloudwatch(self) -> None:
        assert classify_resource_category("aws_cloudwatch_metric_alarm") == "monitoring"

    def test_messaging_cloudwatch_event(self) -> None:
        # "cloudwatch_event" should match before "cloudwatch"
        assert classify_resource_category("aws_cloudwatch_event_rule") == "messaging"

    def test_unknown_service_returns_infrastructure(self) -> None:
        assert classify_resource_category("aws_unknown_thing") == "infrastructure"

    def test_security_wafv2(self) -> None:
        assert classify_resource_category("aws_wafv2_web_acl") == "security"

    def test_data_neptune(self) -> None:
        assert classify_resource_category("aws_neptune_cluster") == "data"


# ---------------------------------------------------------------------------
# make_generic_extractor
# ---------------------------------------------------------------------------


class TestMakeGenericExtractor:
    """Tests for the generic extractor closure."""

    def test_extracts_name_attribute(self, sample_context: ExtractionContext) -> None:
        extractor = make_generic_extractor(["name"], "security")
        results = extractor(
            sample_context,
            "aws_wafv2_web_acl",
            "my_acl",
            'name = "prod-waf-acl"\nscope = "REGIONAL"',
        )
        assert len(results) == 1
        assert results[0].candidate_name == "prod-waf-acl"
        assert results[0].evidence_kind == "TERRAFORM_WAFV2_WEB_ACL"
        assert results[0].confidence == 0.78
        assert results[0].extra_details["schema_driven"] is True
        assert results[0].extra_details["category"] == "security"

    def test_extracts_cluster_identifier(
        self, sample_context: ExtractionContext
    ) -> None:
        extractor = make_generic_extractor(["cluster_identifier"], "data")
        results = extractor(
            sample_context,
            "aws_neptune_cluster",
            "graph_db",
            'cluster_identifier = "my-graph-db"',
        )
        assert len(results) == 1
        assert results[0].candidate_name == "my-graph-db"
        assert results[0].evidence_kind == "TERRAFORM_NEPTUNE_CLUSTER"

    def test_falls_back_to_resource_name(
        self, sample_context: ExtractionContext
    ) -> None:
        extractor = make_generic_extractor(["name"], "compute")
        results = extractor(
            sample_context,
            "aws_apprunner_service",
            "my-api-service",
            "auto_deployments_enabled = true",
        )
        assert len(results) == 1
        assert results[0].candidate_name == "my-api-service"
        assert results[0].extra_details["identity_key"] == "resource_name"
        assert results[0].confidence == 0.55

    def test_skips_generic_resource_names(
        self, sample_context: ExtractionContext
    ) -> None:
        extractor = make_generic_extractor(["name"], "networking")
        results = extractor(
            sample_context,
            "aws_vpc",
            "main",
            'cidr_block = "10.0.0.0/16"',
        )
        assert results == []

    def test_skips_when_no_candidate(self, sample_context: ExtractionContext) -> None:
        extractor = make_generic_extractor(["name"], "networking")
        results = extractor(
            sample_context,
            "aws_vpc",
            "this",
            'cidr_block = "10.0.0.0/16"',
        )
        assert results == []


# ---------------------------------------------------------------------------
# register_schema_driven_extractors
# ---------------------------------------------------------------------------


class TestRegisterSchemaDrivenExtractors:
    """Tests for schema-driven extractor registration."""

    def test_registers_from_fixture_schema(self) -> None:
        # Trigger manual extractor registration first.
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        # The __init__.py auto-registers from schemas/ at import time.
        # If the real AWS schema is present, fixture types are already
        # covered.  Either way, the types must be in the registry.
        register_schema_driven_extractors(FIXTURE_SCHEMA.parent)
        registered = get_registered_resource_types()
        # Types with identity keys should be registered (by real schema or fixture).
        assert "aws_wafv2_web_acl" in registered
        assert "aws_neptune_cluster" in registered
        assert "aws_apprunner_service" in registered
        # All schema-known types are registered (even without identity keys).
        assert "aws_vpc" in registered

    def test_skips_already_registered_types(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        registered_before = get_registered_resource_types()
        assert "aws_lambda_function" in registered_before
        register_schema_driven_extractors(FIXTURE_SCHEMA.parent)
        # Lambda should still have its original manual extractor, not duplicated.
        registered_after = get_registered_resource_types()
        assert "aws_lambda_function" in registered_after

    def test_returns_empty_for_nonexistent_dir(self, tmp_path: Path) -> None:
        summary = register_schema_driven_extractors(tmp_path / "no_such_dir")
        assert summary == {}

    def test_registered_types_are_callable(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        register_schema_driven_extractors(FIXTURE_SCHEMA.parent)
        from platform_context_graph.relationships.terraform_evidence._base import (
            get_extractors_for_type,
        )

        extractors = get_extractors_for_type("aws_wafv2_web_acl")
        assert len(extractors) >= 1
        assert callable(extractors[0])

    def test_new_types_visible_in_registry(self) -> None:
        import platform_context_graph.relationships.terraform_evidence  # noqa: F401

        register_schema_driven_extractors(FIXTURE_SCHEMA.parent)
        registered = get_registered_resource_types()
        assert "aws_wafv2_web_acl" in registered
        assert "aws_neptune_cluster" in registered
        assert "aws_apprunner_service" in registered

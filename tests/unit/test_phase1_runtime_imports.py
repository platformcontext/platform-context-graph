"""Phase 1 guards for runtime modules importing canonical packages."""

from platform_context_graph.content import ingest as content_ingest
from platform_context_graph.content import postgres_queries
from platform_context_graph.query.repositories import (
    content_enrichment_workflows as repository_workflows,
)
from platform_context_graph.relationships import evidence_argocd
from platform_context_graph.relationships import evidence_terraform_support


def test_content_runtime_uses_canonical_templated_detection() -> None:
    """Content modules should import templated detection from content."""
    assert content_ingest.infer_content_metadata.__module__ == (
        "platform_context_graph.content.templated_detection"
    )
    assert postgres_queries.infer_content_metadata.__module__ == (
        "platform_context_graph.content.templated_detection"
    )


def test_repository_runtime_uses_canonical_jenkins_metadata() -> None:
    """Repository workflow enrichment should not import Jenkins helpers from parsers."""
    assert repository_workflows.extract_jenkins_pipeline_metadata.__module__ == (
        "platform_context_graph.automation.jenkins_metadata"
    )


def test_relationship_runtime_uses_canonical_platform_helpers() -> None:
    """Relationship extractors should import platform helpers from resolution."""
    assert evidence_argocd.infer_gitops_platform_id.__module__ == (
        "platform_context_graph.relationships.platform_inference"
    )
    assert evidence_terraform_support.extract_terraform_platform_name.__module__ == (
        "platform_context_graph.relationships.platform_inference"
    )
    assert evidence_terraform_support.infer_terraform_platform_kind.__module__ == (
        "platform_context_graph.relationships.platform_inference"
    )

from __future__ import annotations

from platform_context_graph.query.repositories.content_enrichment_workflow_paths import (
    enrich_workflow_paths,
)


def test_enrich_workflow_paths_skips_delivery_summary_for_empty_local_artifacts(
    monkeypatch,
) -> None:
    """Empty local artifact mappings should not trigger delivery-path summarization."""

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment_workflow_paths.extract_delivery_workflows",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment_workflow_paths.extract_ansible_automation_evidence",
        lambda _repo_root: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.content_enrichment_workflow_paths.summarize_delivery_paths",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("summarize_delivery_paths should not be called")
        ),
    )

    context = {
        "platforms": [],
        "deploys_from": [],
        "discovers_config_in": [],
        "provisioned_by": [],
    }
    enrich_workflow_paths(
        repository={
            "id": "repository:r_demo",
            "name": "demo-repo",
            "path": "/does/not/exist",
            "local_path": "/does/not/exist",
        },
        context=context,
        resolve_repository=lambda _candidate: None,
        local_deployment_artifacts={
            "charts": [],
            "images": [],
            "service_ports": [],
            "gateways": [],
            "k8s_resources": [],
            "kustomize_resources": [],
            "kustomize_patches": [],
            "config_paths": [],
        },
    )

    assert "delivery_paths" not in context

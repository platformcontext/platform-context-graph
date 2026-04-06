"""Workflow and controller-driven enrichment for repository context."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Callable

from .content_enrichment_ansible import extract_ansible_automation_evidence
from .content_enrichment_automation_paths import build_controller_driven_paths
from .content_enrichment_delivery_paths import summarize_delivery_paths
from .content_enrichment_workflows import extract_delivery_workflows


def enrich_workflow_paths(
    *,
    repository: dict[str, Any],
    context: dict[str, Any],
    resolve_repository: Callable[[str], dict[str, Any] | None],
    database: Any = None,
    local_deployment_artifacts: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """Mutate context with workflow, controller-driven, and delivery paths."""

    delivery_workflows = extract_delivery_workflows(
        repository=repository,
        resolve_repository=resolve_repository,
        database=database,
    )
    repo_root = _repo_root(repository)
    ansible_hints = (
        extract_ansible_automation_evidence(repo_root) if repo_root is not None else {}
    )
    if delivery_workflows:
        context["delivery_workflows"] = delivery_workflows
    if ansible_hints:
        controller_driven_paths = build_controller_driven_paths(
            workflow_hints=delivery_workflows,
            ansible_hints=ansible_hints,
            platforms=list(context.get("platforms") or []),
            provisioned_by=list(context.get("provisioned_by") or []),
            infrastructure=(
                context.get("infrastructure")
                if isinstance(context.get("infrastructure"), dict)
                else {}
            ),
        )
        if controller_driven_paths:
            context["controller_driven_paths"] = controller_driven_paths
    elif isinstance(context.get("infrastructure"), dict):
        controller_driven_paths = build_controller_driven_paths(
            workflow_hints=delivery_workflows,
            ansible_hints={},
            platforms=list(context.get("platforms") or []),
            provisioned_by=list(context.get("provisioned_by") or []),
            infrastructure=context["infrastructure"],
        )
        if controller_driven_paths:
            context["controller_driven_paths"] = controller_driven_paths
    if delivery_workflows or local_deployment_artifacts:
        delivery_paths = summarize_delivery_paths(
            delivery_workflows=delivery_workflows,
            controller_driven_paths=list(context.get("controller_driven_paths") or []),
            platforms=list(context.get("platforms") or []),
            deploys_from=list(context.get("deploys_from") or []),
            discovers_config_in=list(context.get("discovers_config_in") or []),
            provisioned_by=list(context.get("provisioned_by") or []),
            deployment_artifacts=local_deployment_artifacts or {},
        )
        if delivery_paths:
            context["delivery_paths"] = delivery_paths


def _repo_root(repository: dict[str, Any]) -> Path | None:
    """Return the local repository root when it exists on disk.

    Ansible enrichment still uses filesystem access for workflow path discovery.
    """

    raw_path = repository.get("local_path") or repository.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    repo_root = Path(raw_path)
    if not repo_root.exists() or not repo_root.is_dir():
        return None
    return repo_root


__all__ = ["enrich_workflow_paths"]

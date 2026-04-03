"""Infrastructure link dispatch helpers."""

from __future__ import annotations

from typing import Any, Iterable


def create_all_infra_links(
    builder: Any, all_file_data: Iterable[dict[str, Any]], *, info_logger_fn: Any
) -> None:
    """Link infrastructure nodes after indexing completes.

    Args:
        builder: ``GraphBuilder`` facade instance.
        all_file_data: Parsed file payloads for the full indexing run.
        info_logger_fn: Info logger callable.
    """
    infra_keys = (
        "k8s_resources",
        "argocd_applications",
        "argocd_applicationsets",
        "crossplane_xrds",
        "crossplane_compositions",
        "crossplane_claims",
        "kustomize_overlays",
        "helm_charts",
        "helm_values",
        "terraform_resources",
        "terraform_modules",
        "terragrunt_configs",
        "cloudformation_resources",
    )
    has_infra = any(
        item
        for file_data in all_file_data
        for key in infra_keys
        for item in file_data.get(key, [])
    )
    if not has_infra:
        return

    info_logger_fn("Creating infrastructure relationships...")
    from .cross_repo_linker import CrossRepoLinker

    linker = CrossRepoLinker(builder.db_manager)
    stats = linker.link_all()
    total = sum(stats.values())
    if total > 0:
        info_logger_fn(
            f"Infrastructure linking: {total} relationships created ({stats})"
        )
    else:
        info_logger_fn("Infrastructure linking: no relationships found")


__all__ = ["create_all_infra_links"]

"""Trace-shaping helpers for ecosystem MCP handlers."""

from __future__ import annotations

from typing import Any

from ....query.environment_normalization import canonical_environment_key
from ....query.environment_normalization import ordered_unique_environment_names


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows with duplicates removed while preserving order."""
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _canonical_source_repositories(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the deduplicated config and deployment source repositories."""

    rows = [
        *list(context.get("deploys_from") or []),
        *list(context.get("discovers_config_in") or []),
    ]
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        identity = str(row.get("id") or row.get("name") or "").strip()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def _split_csv(value: Any) -> list[str]:
    """Return non-empty trimmed CSV tokens from one raw value."""

    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _source_repo_name_hints(
    *,
    source_repositories: list[dict[str, Any]],
    argocd_apps: list[dict[str, Any]],
    argocd_appsets: list[dict[str, Any]],
) -> list[str]:
    """Return portable repository-name hints from canonical and ArgoCD context."""

    names = {str(row["name"]).strip() for row in source_repositories if row.get("name")}
    for row in [*argocd_apps, *argocd_appsets]:
        for raw_repo in _split_csv(row.get("source_repos")):
            candidate = raw_repo.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
            if candidate:
                names.add(candidate)
    return sorted(names)


def _service_name_tokens(service_name: str) -> list[str]:
    """Return stable service-name tokens for cross-tool matching."""

    canonical = service_name.lower().strip()
    variants = {
        canonical,
        canonical.replace("-", "_"),
        canonical.replace("_", "-"),
    }
    return sorted(token for token in variants if token)


def _normalized_environment_names(values: list[str] | None) -> list[str]:
    """Return ordered unique environment names."""

    return ordered_unique_environment_names(list(values or []))


def _environment_truthfulness_note(
    *,
    environments: list[str] | None,
    observed_config_environments: list[str] | None,
) -> str:
    """Return a note that distinguishes runtime-confirmed and config-only envs."""

    runtime = _normalized_environment_names(environments)
    observed = _normalized_environment_names(observed_config_environments)
    if not observed:
        return ""
    if not runtime:
        observed_phrase = ", ".join(observed)
        return (
            f"Configuration references environments {observed_phrase}, "
            "but runtime evidence has not confirmed deployed environments."
        )

    runtime_set = {
        canonical_environment_key(name) or name for name in runtime if str(name).strip()
    }
    extra_config = [
        name
        for name in observed
        if (canonical_environment_key(name) or name) not in runtime_set
    ]
    if not extra_config:
        return ""

    runtime_phrase = ", ".join(runtime)
    extra_phrase = ", ".join(extra_config)
    return (
        f"Confirmed runtime environments: {runtime_phrase}. "
        f"Configuration also references: {extra_phrase}."
    )


def repo_summary_note(
    *,
    limitations: list[str],
    coverage: dict[str, Any] | None,
    environments: list[str] | None = None,
    observed_config_environments: list[str] | None = None,
) -> str:
    """Return a short human-readable note for coverage and environment gaps."""

    base_note = ""
    if "graph_partial" in limitations or "content_partial" in limitations:
        base_note = (
            "Repository coverage is partial; graph/content counts may be incomplete."
        )
    elif "dns_unknown" in limitations and "entrypoint_unknown" in limitations:
        base_note = (
            "DNS and entrypoint evidence are currently unavailable for this repository."
        )
    elif "dns_unknown" in limitations:
        base_note = "DNS evidence is currently unavailable for this repository."
    elif "entrypoint_unknown" in limitations:
        base_note = "Entrypoint evidence is currently unavailable for this repository."
    elif "finalization_incomplete" in limitations:
        finalization_status = str(
            (coverage or {}).get("finalization_status") or ""
        ).strip()
        status_phrase = finalization_status or "pending"
        base_note = (
            f"Repository finalization is {status_phrase}; deployment and relationship "
            f"summaries may still be incomplete."
        )
    elif coverage and coverage.get("completeness_state") == "failed":
        base_note = "Repository coverage failed; runtime and deployment summaries may be incomplete."
    elif limitations:
        base_note = "Repository context has known limitations."

    env_note = _environment_truthfulness_note(
        environments=environments,
        observed_config_environments=observed_config_environments,
    )
    if base_note and env_note:
        return f"{base_note} {env_note}"
    return base_note or env_note


def _direct_deployment_chain_rows(
    deployment_chain: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the direct deployment-chain edges used by the focused trace."""

    direct_relationships = {"DEPLOYS_FROM", "DISCOVERS_CONFIG_IN"}
    return [
        row
        for row in deployment_chain
        if str(row.get("relationship_type") or "").strip() in direct_relationships
    ]


def _focused_trace_note(
    *,
    direct_only: bool,
    max_depth: int | None,
    include_related_module_usage: bool,
) -> str:
    """Return a short note describing how the trace was intentionally narrowed."""

    note_parts: list[str] = []
    if direct_only:
        note_parts.append("Focused trace shows direct deployment evidence only.")
    if max_depth is not None:
        note_parts.append(f"Trace depth is capped at {max_depth}.")
    if not include_related_module_usage:
        note_parts.append("Related module usage is omitted.")
    return " ".join(note_parts)


def _trace_truncation(
    *,
    direct_only: bool,
    max_depth: int | None,
    include_related_module_usage: bool,
) -> dict[str, Any] | None:
    """Return explicit trace-truncation metadata when a focused view is used."""

    if not direct_only and max_depth is None and include_related_module_usage:
        return None

    return {
        "applied": True,
        "omitted_sections": [
            "deployment_chain",
            "terraform_resources",
            "terraform_modules",
            "terragrunt_configs",
            "provisioning_source_chains",
        ],
    }


def _direct_repo_rows(
    rows: list[dict[str, Any]],
    *,
    repository_name: str,
) -> list[dict[str, Any]]:
    """Return rows that belong to the canonical repository itself."""

    if not repository_name:
        return list(rows)
    return [
        row
        for row in rows
        if str(row.get("repository") or "").strip() == repository_name
    ]

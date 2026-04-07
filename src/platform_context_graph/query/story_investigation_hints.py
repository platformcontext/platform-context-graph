"""Shared helpers for lightweight investigation hints in story responses."""

from __future__ import annotations

from typing import Any


def _ordered_unique_names(rows: list[dict[str, Any]]) -> list[str]:
    """Return stable unique names extracted from mixed repository rows."""

    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def build_investigation_hints(
    *,
    subject_name: str,
    deploys_from: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
    environment: str | None = None,
) -> dict[str, Any] | None:
    """Build a small investigation handoff block for story drilldowns."""

    related_repositories = _ordered_unique_names([*deploys_from, *provisioned_by])
    evidence_families: list[str] = []
    if delivery_paths or controller_driven_paths:
        evidence_families.extend(["deployment_controller", "gitops_config"])
    if provisioned_by:
        evidence_families.append("iac_infrastructure")
    if not related_repositories and not evidence_families:
        return None

    args: dict[str, Any] = {"service_name": subject_name}
    if environment:
        args["environment"] = environment
    return {
        "related_repositories": related_repositories,
        "evidence_families": evidence_families,
        "recommended_next_call": {
            "tool": "investigate_service",
            "args": args,
        },
    }


__all__ = ["build_investigation_hints"]

"""High-level deployment overview helpers for ecosystem handlers."""

from typing import Any


def build_deployment_overview(
    *,
    hostnames: list[dict[str, Any]],
    api_surface: dict[str, Any],
    platforms: list[dict[str, Any]],
    delivery_paths: list[dict[str, Any]],
    provisioning_source_chains: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a compact deployment overview for MCP-friendly answer shaping."""

    overview = {
        "internet_entrypoints": _entrypoints_for_visibility(hostnames, "public"),
        "internal_entrypoints": _entrypoints_for_visibility(hostnames, "internal"),
        "api_surface": {
            "docs_routes": list(api_surface.get("docs_routes") or []),
            "api_versions": list(api_surface.get("api_versions") or []),
        },
        "runtime_platforms": [
            {
                "id": row.get("id"),
                "kind": row.get("kind"),
                "provider": row.get("provider"),
                "environment": row.get("environment"),
                "name": row.get("name"),
            }
            for row in platforms
            if isinstance(row, dict)
        ],
        "delivery_paths": [
            {
                "path_kind": row.get("path_kind"),
                "controller": row.get("controller"),
                "delivery_mode": row.get("delivery_mode"),
                "summary": row.get("summary"),
                "automation_repositories": list(
                    row.get("automation_repositories") or []
                ),
                "deployment_sources": list(row.get("deployment_sources") or []),
                "config_sources": list(row.get("config_sources") or []),
                "provisioning_repositories": list(
                    row.get("provisioning_repositories") or []
                ),
                "platforms": list(row.get("platforms") or []),
                "environments": list(row.get("environments") or []),
            }
            for row in delivery_paths
            if isinstance(row, dict)
        ],
    }
    if provisioning_source_chains:
        overview["provisioning_source_chains"] = list(provisioning_source_chains)
    return overview


def _entrypoints_for_visibility(
    hostnames: list[dict[str, Any]],
    visibility: str,
) -> list[dict[str, Any]]:
    """Return simplified hostname rows for one visibility class."""

    return [
        {
            "hostname": row.get("hostname"),
            "visibility": row.get("visibility"),
        }
        for row in hostnames
        if isinstance(row, dict) and str(row.get("visibility") or "").strip() == visibility
    ]

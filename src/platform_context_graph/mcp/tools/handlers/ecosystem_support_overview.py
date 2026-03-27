"""High-level deployment overview helpers for ecosystem handlers."""

from typing import Any


def build_deployment_overview(
    *,
    hostnames: list[dict[str, Any]],
    api_surface: dict[str, Any],
    platforms: list[dict[str, Any]],
    delivery_paths: list[dict[str, Any]],
    provisioning_source_chains: list[dict[str, Any]] | None = None,
    k8s_resources: list[dict[str, Any]] | None = None,
    crossplane_claims: list[dict[str, Any]] | None = None,
    terraform_resources: list[dict[str, Any]] | None = None,
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
    network_signals = _build_network_signals(
        k8s_resources=k8s_resources or [],
        crossplane_claims=crossplane_claims or [],
        terraform_resources=terraform_resources or [],
    )
    if network_signals:
        overview["network_signals"] = network_signals
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


def _build_network_signals(
    *,
    k8s_resources: list[dict[str, Any]],
    crossplane_claims: list[dict[str, Any]],
    terraform_resources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build compact network and infrastructure routing signals."""

    signals: dict[str, Any] = {}
    if k8s_resources:
        signals["kubernetes"] = [
            {
                "name": row.get("name"),
                "kind": row.get("kind"),
                "repository": row.get("repository"),
                "file": row.get("file"),
            }
            for row in k8s_resources
            if isinstance(row, dict)
        ]
    if crossplane_claims:
        signals["crossplane"] = [
            {
                "claim_name": row.get("claim_name"),
                "claim_kind": row.get("claim_kind"),
                "file": row.get("file"),
            }
            for row in crossplane_claims
            if isinstance(row, dict)
        ]
    if terraform_resources:
        signals["terraform"] = [
            {
                "name": row.get("name"),
                "resource_type": row.get("resource_type"),
                "repository": row.get("repository"),
                "file": row.get("file"),
            }
            for row in terraform_resources
            if isinstance(row, dict)
        ]
    return signals

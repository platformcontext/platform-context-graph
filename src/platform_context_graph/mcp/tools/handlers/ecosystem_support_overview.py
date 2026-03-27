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
    terraform_modules: list[dict[str, Any]] | None = None,
    deployment_artifacts: dict[str, Any] | None = None,
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
    service_variants = _build_service_variants(terraform_modules or [])
    if service_variants:
        overview["service_variants"] = service_variants
    if deployment_artifacts:
        compact_artifacts = {
            "charts": list(deployment_artifacts.get("charts") or []),
            "images": list(deployment_artifacts.get("images") or []),
            "service_ports": list(deployment_artifacts.get("service_ports") or []),
            "gateways": list(deployment_artifacts.get("gateways") or []),
        }
        compact_artifacts = {
            key: value for key, value in compact_artifacts.items() if value
        }
        if compact_artifacts:
            overview["deployment_artifacts"] = compact_artifacts
    network_signals = _build_network_signals(
        k8s_resources=k8s_resources or [],
        crossplane_claims=crossplane_claims or [],
        terraform_resources=terraform_resources or [],
    )
    if network_signals:
        overview["network_signals"] = network_signals
    deployment_controllers = _build_deployment_controllers(
        delivery_paths=delivery_paths,
        terraform_resources=terraform_resources or [],
        terraform_modules=terraform_modules or [],
        provisioning_source_chains=provisioning_source_chains or [],
    )
    if deployment_controllers:
        overview["deployment_controllers"] = deployment_controllers
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


def _build_service_variants(terraform_modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build compact service-variant rows from Terraform module matches."""

    variants: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in terraform_modules:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        repository = str(row.get("repository") or "").strip()
        module_source = str(row.get("source") or "").strip()
        version = str(row.get("version") or "").strip()
        if not name or not repository:
            continue
        key = (name, repository, module_source, version)
        if key in seen:
            continue
        seen.add(key)
        variants.append(
            {
                "name": name,
                "repository": repository,
                "module_source": module_source,
                "version": version,
            }
        )
    return variants


def _build_deployment_controllers(
    *,
    delivery_paths: list[dict[str, Any]],
    terraform_resources: list[dict[str, Any]],
    terraform_modules: list[dict[str, Any]],
    provisioning_source_chains: list[dict[str, Any]],
) -> list[str]:
    """Return ordered deployment-controller hints from delivery and infra signals."""

    controllers: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        """Append one normalized controller hint once."""

        normalized = value.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        controllers.append(normalized)

    for row in delivery_paths:
        if not isinstance(row, dict):
            continue
        controller = str(row.get("controller") or "").strip()
        if controller:
            add(controller)
    if terraform_resources or terraform_modules or provisioning_source_chains:
        terraform_types = {
            str(row.get("resource_type") or "").strip().lower()
            for row in terraform_resources
            if isinstance(row, dict)
        }
        if any(resource_type.startswith("aws_codedeploy_") for resource_type in terraform_types):
            add("codedeploy")
        add("terraform")
    return controllers

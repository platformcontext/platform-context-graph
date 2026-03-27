"""High-level deployment overview helpers for ecosystem handlers."""

from typing import Any

from .ecosystem_support_overview_story import build_topology_story


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
    consumer_repositories: list[dict[str, Any]] | None = None,
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
                "platform_kinds": list(row.get("platform_kinds") or []),
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
    deployment_story = _build_deployment_story(overview["delivery_paths"])
    if deployment_story:
        overview["deployment_story"] = deployment_story
    if provisioning_source_chains:
        overview["provisioning_source_chains"] = list(provisioning_source_chains)
    if consumer_repositories:
        overview["consumer_repositories"] = [
            {
                "repository": row.get("repository"),
                "evidence_kinds": list(row.get("evidence_kinds") or []),
                "sample_paths": list(row.get("sample_paths") or []),
            }
            for row in consumer_repositories
            if isinstance(row, dict)
        ]
    shared_config_paths = _build_shared_config_paths(deployment_artifacts or {})
    if shared_config_paths:
        overview["shared_config_paths"] = shared_config_paths
    topology_story = build_topology_story(
        hostnames=overview["internet_entrypoints"],
        api_surface=overview["api_surface"],
        deployment_story=deployment_story,
        shared_config_paths=shared_config_paths,
        consumer_repositories=overview.get("consumer_repositories", []),
    )
    if topology_story:
        overview["topology_story"] = topology_story
    service_variants = _build_service_variants(terraform_modules or [])
    if service_variants:
        overview["service_variants"] = service_variants
    if deployment_artifacts:
        compact_artifacts = {
            "charts": list(deployment_artifacts.get("charts") or []),
            "images": list(deployment_artifacts.get("images") or []),
            "service_ports": list(deployment_artifacts.get("service_ports") or []),
            "gateways": list(deployment_artifacts.get("gateways") or []),
            "kustomize_resources": list(
                deployment_artifacts.get("kustomize_resources") or []
            ),
            "kustomize_patches": list(
                deployment_artifacts.get("kustomize_patches") or []
            ),
            "config_paths": list(deployment_artifacts.get("config_paths") or []),
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


def build_story_lines(
    *,
    deployment_overview: dict[str, Any] | None,
    note: str = "",
) -> list[str]:
    """Return a top-level MCP-friendly story derived from overview and notes."""

    if not isinstance(deployment_overview, dict):
        deployment_overview = {}

    candidates = deployment_overview.get("topology_story")
    if not candidates:
        candidates = deployment_overview.get("deployment_story")

    lines: list[str] = []
    seen: set[str] = set()
    for value in list(candidates or []):
        line = str(value).strip()
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)

    normalized_note = str(note).strip()
    if normalized_note and normalized_note not in seen:
        lines.append(normalized_note)
    return lines


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
    seen: set[tuple[str, str, str, str, str, str, str, str, str]] = set()
    for row in terraform_modules:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        repository = str(row.get("repository") or "").strip()
        module_source = str(row.get("source") or "").strip()
        version = str(row.get("version") or "").strip()
        deployment_name = str(row.get("deployment_name") or "").strip()
        repo_name = str(row.get("repo_name") or "").strip()
        create_deploy = _normalize_optional_bool(row.get("create_deploy"))
        cluster_name = str(row.get("cluster_name") or "").strip()
        zone_id = str(row.get("zone_id") or "").strip()
        entry_point = str(row.get("deploy_entry_point") or "").strip()
        if not name or not repository:
            continue
        key = (
            name,
            repository,
            module_source,
            version,
            deployment_name,
            repo_name,
            str(create_deploy),
            cluster_name,
            entry_point,
        )
        if key in seen:
            continue
        seen.add(key)
        variant = {
            "name": name,
            "repository": repository,
            "module_source": module_source,
            "version": version,
        }
        if deployment_name:
            variant["deployment_name"] = deployment_name
        if repo_name:
            variant["repo_name"] = repo_name
        if create_deploy is not None:
            variant["create_deploy"] = create_deploy
        if cluster_name:
            variant["cluster_name"] = cluster_name
        if zone_id:
            variant["zone_id"] = zone_id
        if entry_point:
            variant["entry_point"] = entry_point
        variants.append(variant)
    return variants


def _normalize_optional_bool(value: Any) -> bool | None:
    """Return a normalized bool for Terraform-style truthy values when possible."""

    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


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


def _build_deployment_story(delivery_paths: list[dict[str, Any]]) -> list[str]:
    """Render short human-readable end-to-end deployment story lines."""

    lines: list[str] = []
    for row in delivery_paths:
        if not isinstance(row, dict):
            continue
        controller = _controller_label(str(row.get("controller") or ""))
        automation = list(row.get("automation_repositories") or [])
        deployment_sources = list(row.get("deployment_sources") or [])
        provisioning_repositories = list(row.get("provisioning_repositories") or [])
        platform_kinds = [str(value).strip().upper() for value in row.get("platform_kinds") or [] if str(value).strip()]
        environments = [str(value).strip() for value in row.get("environments") or [] if str(value).strip()]

        line = controller
        if automation:
            line += f" via {', '.join(automation)}"
        if deployment_sources:
            line += f" deploys from {', '.join(deployment_sources)}"
        elif provisioning_repositories:
            line += f" deploys through {', '.join(provisioning_repositories)}"
        else:
            line += " deploys"
        if platform_kinds:
            line += f" onto {'/'.join(platform_kinds)}"
        if environments:
            line += f" in {', '.join(environments)}"
        lines.append(line + ".")
    return lines


def _controller_label(value: str) -> str:
    """Return a display label for one deployment controller."""

    normalized = value.strip().lower()
    if normalized == "github_actions":
        return "GitHub Actions"
    if normalized == "jenkins":
        return "Jenkins"
    return value.replace("_", " ").strip() or "Unknown controller"


def _build_shared_config_paths(
    deployment_artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return config paths that appear across multiple source repositories."""

    grouped: dict[str, set[str]] = {}
    for row in deployment_artifacts.get("config_paths") or []:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        source_repo = str(row.get("source_repo") or "").strip()
        if not path or not source_repo:
            continue
        grouped.setdefault(path, set()).add(source_repo)
    return [
        {
            "path": path,
            "source_repositories": sorted(source_repositories),
        }
        for path, source_repositories in sorted(grouped.items())
        if len(source_repositories) > 1
    ]

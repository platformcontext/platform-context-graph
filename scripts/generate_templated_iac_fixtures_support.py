"""Support helpers for generating sanitized templated IaC fixture repos."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import shutil
from typing import Callable

_WEBHOOK_RE = re.compile(r"https://hooks\.slack\.com/services/[^\s\"']+")
_PORTALS_BLOCK_RE = re.compile(
    r"(?s){% set portals = \[\n.*?\n\] %}",
)
_PORTALS_TEMPLATE = """{% set portals = [
  'portal-alpha',
  'portal-bravo',
  'portal-charlie',
  'portal-delta',
  'portal-echo',
  'portal-foxtrot',
  'portal-golf',
  'portal-hotel'
] %}"""
_GLOBAL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("boatsgroup.pe.jfrog.io/bg-docker/platformcontextgraph", "registry.example.invalid/example/platform-service"),
    ("boatsgroup.pe.jfrog.io/artifactory/bg-generic", "artifacts.example.invalid/generic"),
    ("boatsgroupwebsites.com", "examplewebsites.invalid"),
    ("yachtworld.com", "marketplace.example.invalid"),
    ("platformcontextgraph", "templated-runtime"),
    ("boatsgroup", "exampleco"),
    ("bg-dp", "demo-dp"),
)


@dataclass(frozen=True, slots=True)
class FixtureFileSpec:
    """One source file copied into the templated IaC fixture corpus."""

    source: Path
    target_repo: str
    target_path: str
    family: str
    artifact_type: str
    transform: str = "default"
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FixtureFileRecord:
    """Serializable metadata for one generated fixture file."""

    family: str
    artifact_type: str
    source: str
    target: str
    notes: tuple[str, ...]


def default_fixture_specs() -> list[FixtureFileSpec]:
    """Return the curated real-source file set used for sanitized fixtures."""

    home = Path.home()
    return [
        FixtureFileSpec(
            source=home / "repos/mobius/iac-eks-pcg/chart/Chart.yaml",
            target_repo="example-platform-chart",
            target_path="chart/Chart.yaml",
            family="helm_go_template",
            artifact_type="helm_chart",
            transform="helm_chart",
            notes=("genericize chart identity",),
        ),
        FixtureFileSpec(
            source=home / "repos/mobius/iac-eks-pcg/chart/values.yaml",
            target_repo="example-platform-chart",
            target_path="chart/values.yaml",
            family="helm_go_template",
            artifact_type="helm_values",
            transform="helm_values",
            notes=("replace registry, org, and secret names",),
        ),
        FixtureFileSpec(
            source=home / "repos/mobius/iac-eks-pcg/chart/templates/_helpers.tpl",
            target_repo="example-platform-chart",
            target_path="chart/templates/_helpers.tpl",
            family="helm_go_template",
            artifact_type="helm_helper_tpl",
            notes=("preserve Go-template helpers",),
        ),
        FixtureFileSpec(
            source=home / "repos/mobius/iac-eks-pcg/chart/templates/deployment.yaml",
            target_repo="example-platform-chart",
            target_path="chart/templates/deployment.yaml",
            family="helm_go_template",
            artifact_type="go_template_yaml",
            notes=("preserve Go-template YAML control flow",),
        ),
        FixtureFileSpec(
            source=home
            / "repos/ansible-automate/automate-mws/roles/portal-websites/templates/portal-dmmwebsites.conf.j2",
            target_repo="example-ansible-templates",
            target_path="roles/web/templates/site.conf.j2",
            family="ansible_jinja",
            artifact_type="nginx_config_template",
            transform="ansible_conf",
            notes=("replace company domains and custom header names",),
        ),
        FixtureFileSpec(
            source=home
            / "repos/ansible-automate/automate-build-golden-ami/roles/build-ami/templates/Dockerfile.j2",
            target_repo="example-ansible-templates",
            target_path="roles/builder/templates/Dockerfile.j2",
            family="ansible_jinja",
            artifact_type="dockerfile_template",
            notes=("replace private artifact registry",),
        ),
        FixtureFileSpec(
            source=home
            / "repos/services/bg-dagster/Dockerfile",
            target_repo="example-dagster-assets",
            target_path="Dockerfile",
            family="dagster_jinja_yaml",
            artifact_type="dockerfile",
            notes=("preserve a plain Dockerfile for raw-text ingestion",),
        ),
        FixtureFileSpec(
            source=home
            / "repos/services/bg-dagster/bg_data_platform/assets/data_lakehouse/branchio_ingestion.yaml",
            target_repo="example-dagster-assets",
            target_path="assets/data_lakehouse/branch_ingestion.yaml",
            family="dagster_jinja_yaml",
            artifact_type="jinja_yaml",
            notes=("preserve Jinja loops over YAML structures",),
        ),
        FixtureFileSpec(
            source=home
            / "repos/services/bg-dagster/bg_data_platform/assets/data_quality/ga4_dq_checks.yaml",
            target_repo="example-dagster-assets",
            target_path="assets/data_quality/analytics_checks.yaml",
            family="dagster_jinja_yaml",
            artifact_type="jinja_yaml",
            transform="dagster_quality",
            notes=("replace portal names and scrub webhook",),
        ),
        FixtureFileSpec(
            source=home
            / "repos/terraform-modules/terraform-snapshots/modules/ecs/application-cloudmap/templates/ecs/container.tpl",
            target_repo="example-terraform-templates",
            target_path="templates/ecs/container.tpl",
            family="terraform_template_text",
            artifact_type="terraform_template_text",
            notes=("preserve Terraform interpolation placeholders",),
        ),
    ]


def _apply_global_replacements(content: str) -> str:
    """Replace obviously company-specific domains, orgs, and registries."""

    updated = content
    for needle, replacement in _GLOBAL_REPLACEMENTS:
        updated = updated.replace(needle, replacement)
    return _WEBHOOK_RE.sub(
        "https://hooks.example.invalid/services/TEAM/CHANNEL/TOKEN",
        updated,
    )


def _sanitize_helm_chart(content: str) -> str:
    """Genericize Helm chart naming while preserving chart structure."""

    content = content.replace("templated-runtime", "template-platform-service")
    return content.replace(
        "PlatformContextGraph application layer with separate API and repository ingester runtimes.",
        "Example platform service with separate API and repository ingester runtimes.",
    )


def _sanitize_helm_values(content: str) -> str:
    """Genericize Helm values without changing the YAML/templating shape."""

    replacements = (
        ("templated-runtime", "template-platform-service"),
        ("platform_context_graph", "template_platform_service"),
        ("PCG_", "APP_"),
        ("githubOrg: exampleco", "githubOrg: demo-org"),
    )
    updated = content
    for needle, replacement in replacements:
        updated = updated.replace(needle, replacement)
    return updated


def _sanitize_ansible_conf(content: str) -> str:
    """Sanitize company-branded nginx config markers while keeping Jinja intact."""

    replacements = (
        ("cobrokerage", "partner-sites"),
        ("$bg_proto", "$edge_proto"),
        ("map $http_x_forwarded_proto $bg_proto", "map $http_x_forwarded_proto $edge_proto"),
        ("X-dmmserver-host", "X-example-server-host"),
        ("X-dmmserver-name", "X-example-server-name"),
        ("www.${host}", "www.${host}"),
    )
    updated = content
    for needle, replacement in replacements:
        updated = updated.replace(needle, replacement)
    return updated


def _sanitize_dagster_quality(content: str) -> str:
    """Replace real portal names and webhooks with generic placeholders."""

    content = _PORTALS_BLOCK_RE.sub(_PORTALS_TEMPLATE, content)
    return content.replace(
        "ga4_sanitized_unified_web_portals_253526969",
        "analytics_sanitized_unified_web_portals_000000001",
    )


_TRANSFORMS: dict[str, Callable[[str], str]] = {
    "default": lambda content: content,
    "helm_chart": _sanitize_helm_chart,
    "helm_values": _sanitize_helm_values,
    "ansible_conf": _sanitize_ansible_conf,
    "dagster_quality": _sanitize_dagster_quality,
}


def sanitize_fixture_text(content: str, *, transform: str) -> str:
    """Apply deterministic scrubbing for one selected fixture file."""

    content = _apply_global_replacements(content)
    sanitizer = _TRANSFORMS[transform]
    return sanitizer(content)


def _manifest_path(output_root: Path) -> Path:
    """Return the manifest path for one generated fixture corpus."""

    return output_root / "manifest.json"


def _readme_path(output_root: Path) -> Path:
    """Return the human-readable README path for one generated fixture corpus."""

    return output_root / "README.md"


def _build_readme(records: list[FixtureFileRecord]) -> str:
    """Render a compact README describing the generated fixture corpus."""

    grouped: dict[str, list[FixtureFileRecord]] = {}
    for record in records:
        grouped.setdefault(record.family, []).append(record)

    lines = [
        "# Templated IaC Fixture Corpus",
        "",
        "Sanitized from local real-world source files under `~/repos`.",
        "These fixtures preserve templating structure while removing company domains, org names, registries, and secrets.",
        "",
        "Regenerate with:",
        "",
        "```bash",
        "python3 scripts/generate_templated_iac_fixtures.py",
        "```",
        "",
    ]
    for family in sorted(grouped):
        lines.append(f"## {family}")
        lines.append("")
        for record in sorted(grouped[family], key=lambda item: item.target):
            lines.append(f"- `{record.target}`")
            lines.append(f"  - Source: `{record.source}`")
            if record.notes:
                lines.append(f"  - Notes: {', '.join(record.notes)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_fixture_corpus(
    output_root: Path,
    *,
    specs: list[FixtureFileSpec] | None = None,
) -> list[FixtureFileRecord]:
    """Generate the sanitized templated IaC fixture corpus on disk."""

    selected_specs = specs or default_fixture_specs()
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    records: list[FixtureFileRecord] = []
    for spec in selected_specs:
        content = spec.source.read_text(encoding="utf-8")
        sanitized = sanitize_fixture_text(content, transform=spec.transform)
        target_path = output_root / spec.target_repo / spec.target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(sanitized, encoding="utf-8")
        records.append(
            FixtureFileRecord(
                family=spec.family,
                artifact_type=spec.artifact_type,
                source=_display_source(spec.source),
                target=str(Path(spec.target_repo) / spec.target_path),
                notes=spec.notes,
            )
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repos": sorted({spec.target_repo for spec in selected_specs}),
        "files": [asdict(record) for record in records],
    }
    _manifest_path(output_root).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _readme_path(output_root).write_text(_build_readme(records), encoding="utf-8")
    return records


def _display_source(path: Path) -> str:
    """Render source paths relative to the user's home directory when possible."""

    home = Path.home()
    try:
        return str(Path("~") / path.relative_to(home))
    except ValueError:
        return str(path)

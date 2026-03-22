"""Feature-matrix helpers for parser capability contracts."""

from __future__ import annotations

from .models import (
    AUTO_GENERATED_BANNER,
    CODE_MATRIX_BUCKET_FALLBACK_IDS,
    CODE_MATRIX_CAPABILITY_ALIASES,
    CapabilityStatus,
    GraphSurface,
    LanguageCapabilitySpec,
)


def render_feature_matrix(specs: list[LanguageCapabilitySpec]) -> str:
    """Render the generated parser feature matrix."""

    code_specs = [spec for spec in specs if spec["family"] == "language"]
    iac_specs = [spec for spec in specs if spec["family"] == "iac"]

    lines = [
        "# Parser Feature Matrix",
        "",
        AUTO_GENERATED_BANNER,
        "",
        "## Language Parsers",
        "",
        "| Parser | Parser Class | Functions | Classes | Interfaces | Traits | Imports | Calls | Variables | Structs | Enums | Macros | Unit Coverage | Integration Coverage | Fixture |",
        "|--------|--------------|-----------|---------|------------|--------|---------|-------|-----------|---------|-------|--------|---------------|----------------------|---------|",
    ]
    for spec in code_specs:
        lines.append(
            "| {title} | `{parser}` | {functions} | {classes} | {interfaces} | {traits} | {imports} | {calls} | {variables} | {structs} | {enums} | {macros} | {unit} | {integration} | `{fixture}` |".format(
                title=spec["title"].replace(" Parser", ""),
                parser=spec["parser"],
                functions=_matrix_status(spec, "functions"),
                classes=_matrix_status(spec, "classes"),
                interfaces=_matrix_status(spec, "interfaces"),
                traits=_matrix_status(spec, "traits"),
                imports=_matrix_status(spec, "imports"),
                calls=_matrix_status(spec, "function_calls"),
                variables=_matrix_status(spec, "variables"),
                structs=_matrix_status(spec, "structs"),
                enums=_matrix_status(spec, "enums"),
                macros=_matrix_status(spec, "macros"),
                unit=_coverage_count(spec, "unit"),
                integration=_coverage_count(spec, "integration"),
                fixture=spec["fixture_repo"],
            )
        )

    lines.extend(
        [
            "",
            "## IaC Parsers",
            "",
            "| Parser | Parser Class | Resources | Variables | Outputs | Modules | Unit Coverage | Integration Coverage | Fixture |",
            "|--------|--------------|-----------|-----------|---------|---------|---------------|----------------------|---------|",
        ]
    )
    for spec in iac_specs:
        lines.append(
            "| {title} | `{parser}` | {resources} | {variables} | {outputs} | {modules} | {unit} | {integration} | `{fixture}` |".format(
                title=spec["title"].replace(" Parser", ""),
                parser=spec["parser"],
                resources=_iac_status(
                    spec,
                    (
                        "terraform_resources",
                        "k8s_resources",
                        "argocd_applications",
                        "crossplane_xrds",
                        "helm_charts",
                        "kustomize_overlays",
                        "cloudformation_resources",
                        "terragrunt_configs",
                    ),
                ),
                variables=_iac_status(
                    spec, ("terraform_variables", "cloudformation_parameters")
                ),
                outputs=_iac_status(
                    spec, ("terraform_outputs", "cloudformation_outputs")
                ),
                modules=_iac_status(
                    spec,
                    (
                        "terraform_modules",
                        "terraform_data_sources",
                        "helm_values",
                        "argocd_applicationsets",
                        "crossplane_compositions",
                        "crossplane_claims",
                    ),
                ),
                unit=_coverage_count(spec, "unit"),
                integration=_coverage_count(spec, "integration"),
                fixture=spec["fixture_repo"],
            )
        )

    return "\n".join(lines) + "\n"


def render_graph_surface(surface: GraphSurface) -> str:
    """Render a graph surface descriptor as compact Markdown text."""

    kind = surface.get("kind", "none")
    target = surface.get("target")
    if not target:
        return kind
    return f"{kind}:{target}"


def _matrix_status(spec: LanguageCapabilitySpec, capability_id: str) -> str:
    """Return matrix status symbol for a named code capability."""

    status = _code_capability_status(spec, capability_id)
    if status is None:
        return "-"
    if status == "supported":
        return "Y"
    return "P"


def _iac_status(spec: LanguageCapabilitySpec, capability_ids: tuple[str, ...]) -> str:
    """Return matrix status symbol across a set of IaC capability IDs."""

    statuses = [
        _iac_capability_status(spec, capability_id) for capability_id in capability_ids
    ]
    statuses = [status for status in statuses if status is not None]
    if not statuses:
        return "-"
    if "supported" in statuses:
        return "Y"
    return "P"


def _normalized_capability_id(value: str) -> str:
    """Return a stable comparison token for one capability identifier."""

    return value.replace("-", "_")


def _status_from_matches(statuses: list[str]) -> CapabilityStatus | None:
    """Collapse one or more status strings into a matrix summary."""

    if not statuses:
        return None
    if "supported" in statuses:
        return "supported"
    if "partial" in statuses:
        return "partial"
    return "unsupported"


def _code_capability_status(
    spec: LanguageCapabilitySpec, capability_id: str
) -> CapabilityStatus | None:
    """Return the status summary for one code-matrix capability column."""

    normalized_target = _normalized_capability_id(capability_id)
    explicit_ids = CODE_MATRIX_CAPABILITY_ALIASES.get(
        normalized_target, {normalized_target}
    )
    statuses: list[str] = []
    for capability in spec["capabilities"]:
        normalized_id = _normalized_capability_id(capability["id"])
        if normalized_id in explicit_ids:
            statuses.append(capability["status"])
            continue
        if (
            normalized_target in CODE_MATRIX_BUCKET_FALLBACK_IDS
            and capability["extracted_bucket"] == capability_id
        ):
            statuses.append(capability["status"])
    return _status_from_matches(statuses)


def _iac_capability_status(
    spec: LanguageCapabilitySpec, capability_id: str
) -> CapabilityStatus | None:
    """Return the status summary for one IaC-matrix capability column."""

    statuses: list[str] = []
    for capability in spec["capabilities"]:
        if (
            capability["id"] == capability_id
            or capability["extracted_bucket"] == capability_id
        ):
            statuses.append(capability["status"])
    return _status_from_matches(statuses)


def _coverage_count(spec: LanguageCapabilitySpec, ref_type: str) -> str:
    """Return coverage fraction text for a capability spec."""

    key = "unit_test" if ref_type == "unit" else "integration_test"
    supported_capabilities = [
        capability
        for capability in spec["capabilities"]
        if capability.get("status") == "supported"
    ]
    if not supported_capabilities:
        return "0/0"

    covered = sum(1 for capability in supported_capabilities if capability.get(key))
    return f"{covered}/{len(supported_capabilities)}"

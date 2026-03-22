"""Helpers for canonical parser capability specs and generated docs."""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

AUTO_GENERATED_BANNER = "This file is auto-generated. Do not edit manually."
SUPPORTED_STATUSES = {"supported", "partial", "unsupported"}
MATRIX_CAPABILITY_IDS = (
    "functions",
    "classes",
    "interfaces",
    "traits",
    "imports",
    "function_calls",
    "variables",
    "structs",
    "enums",
    "macros",
)
MATRIX_IAC_CAPABILITY_IDS = (
    "terraform_resources",
    "terraform_variables",
    "terraform_outputs",
    "terraform_modules",
    "terraform_data_sources",
    "terragrunt_configs",
    "helm_charts",
    "helm_values",
    "kustomize_overlays",
    "argocd_applications",
    "argocd_applicationsets",
    "crossplane_xrds",
    "crossplane_compositions",
    "crossplane_claims",
    "k8s_resources",
    "cloudformation_resources",
    "cloudformation_parameters",
    "cloudformation_outputs",
)


def repo_root(default: Path | None = None) -> Path:
    """Return the repository root for capability spec operations."""

    if default is not None:
        return default.resolve()
    return Path(__file__).resolve().parents[4]


def specs_dir(root: Path | None = None) -> Path:
    """Return the directory containing canonical parser capability specs."""

    return (
        repo_root(root)
        / "src"
        / "platform_context_graph"
        / "tools"
        / "parser_capabilities"
        / "specs"
    )


def load_language_capability_specs(root: Path | None = None) -> list[dict[str, Any]]:
    """Load all parser capability specs from YAML files on disk."""

    resolved_root = repo_root(root)
    specs: list[dict[str, Any]] = []
    for path in sorted(specs_dir(resolved_root).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["spec_path"] = path.relative_to(resolved_root).as_posix()
        specs.append(data)
    return sorted(specs, key=lambda spec: spec["language"])


def validate_language_capability_specs(root: Path | None = None) -> list[str]:
    """Return a list of spec validation errors."""

    resolved_root = repo_root(root)
    errors: list[str] = []
    for spec in load_language_capability_specs(resolved_root):
        errors.extend(_validate_spec(resolved_root, spec))
    return errors


def render_language_doc(spec: dict[str, Any]) -> str:
    """Render one language capability spec into Markdown."""

    lines = [
        f"# {spec['title']}",
        "",
        AUTO_GENERATED_BANNER,
        f"Canonical source: `{spec['spec_path']}`",
        "",
        "## Parser Contract",
        f"- Language: `{spec['language']}`",
        f"- Family: `{spec['family']}`",
        f"- Parser: `{spec['parser']}`",
        f"- Entrypoint: `{spec['parser_entrypoint']}`",
        f"- Fixture repo: `{spec['fixture_repo']}`",
        f"- Unit test suite: `{spec['unit_test_file']}`",
        f"- Integration test suite: `{spec['integration_test_suite']}`",
        "",
        "## Capability Checklist",
        "| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |",
        "|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|",
    ]

    for capability in spec["capabilities"]:
        lines.append(
            "| {name} | `{id}` | {status} | `{bucket}` | `{fields}` | `{surface}` | `{unit}` | `{integration}` | {rationale} |".format(
                name=capability["name"],
                id=capability["id"],
                status=capability["status"],
                bucket=capability["extracted_bucket"],
                fields=", ".join(capability["required_fields"]),
                surface=_render_graph_surface(capability["graph_surface"]),
                unit=capability["unit_test"],
                integration=capability["integration_test"],
                rationale=capability.get("rationale", "-"),
            )
        )

    lines.extend(["", "## Known Limitations"])
    for limitation in spec.get("known_limitations", []):
        lines.append(f"- {limitation}")

    return "\n".join(lines) + "\n"


def render_feature_matrix(specs: list[dict[str, Any]]) -> str:
    """Render a generated parser feature matrix from capability specs."""

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


def expected_generated_language_docs(
    root: Path | None = None,
) -> dict[str, str]:
    """Return the expected generated docs keyed by repo-relative path."""

    resolved_root = repo_root(root)
    specs = load_language_capability_specs(resolved_root)
    docs = {spec["doc_path"]: render_language_doc(spec) for spec in specs}
    docs["docs/docs/languages/feature-matrix.md"] = render_feature_matrix(specs)
    return docs


def write_generated_language_docs(
    root: Path | None = None, *, check: bool = False
) -> list[str]:
    """Write generated language docs or report drift when ``check`` is set."""

    resolved_root = repo_root(root)
    changed: list[str] = []
    for relative_path, expected_content in expected_generated_language_docs(
        resolved_root
    ).items():
        target = resolved_root / relative_path
        current = target.read_text(encoding="utf-8") if target.exists() else None
        if current == expected_content:
            continue
        changed.append(relative_path)
        if not check:
            target.write_text(expected_content, encoding="utf-8")
    return changed


def _validate_spec(root: Path, spec: dict[str, Any]) -> list[str]:
    """Validate one parser capability spec payload."""

    errors: list[str] = []
    required_keys = {
        "language",
        "title",
        "family",
        "parser",
        "parser_entrypoint",
        "doc_path",
        "fixture_repo",
        "unit_test_file",
        "integration_test_suite",
        "capabilities",
        "known_limitations",
        "spec_path",
    }
    missing = sorted(required_keys - spec.keys())
    if missing:
        return [f"{spec.get('spec_path', '<unknown>')}: missing keys {missing}"]

    for key in ("fixture_repo", "unit_test_file"):
        if not (root / spec[key]).exists():
            errors.append(f"{spec['spec_path']}: missing path {spec[key]}")

    doc_path = root / spec["doc_path"]
    if doc_path.suffix != ".md":
        errors.append(f"{spec['spec_path']}: doc_path must point to a Markdown file")
    if not doc_path.parent.exists():
        errors.append(
            f"{spec['spec_path']}: doc_path parent does not exist {doc_path.parent.relative_to(root)}"
        )

    if spec["family"] not in {"language", "iac"}:
        errors.append(
            f"{spec['spec_path']}: family must be 'language' or 'iac', got {spec['family']}"
        )

    seen_ids: set[str] = set()
    for capability in spec["capabilities"]:
        errors.extend(_validate_capability(root, spec["spec_path"], capability))
        capability_id = capability.get("id")
        if capability_id in seen_ids:
            errors.append(
                f"{spec['spec_path']}: duplicate capability id {capability_id}"
            )
        if capability_id is not None:
            seen_ids.add(capability_id)

    return errors


def _validate_capability(
    root: Path, spec_path: str, capability: dict[str, Any]
) -> list[str]:
    """Validate one capability entry."""

    errors: list[str] = []
    required_keys = {
        "id",
        "name",
        "status",
        "extracted_bucket",
        "required_fields",
        "graph_surface",
        "unit_test",
        "integration_test",
    }
    missing = sorted(required_keys - capability.keys())
    if missing:
        return [f"{spec_path}: capability missing keys {missing}"]

    if capability["status"] not in SUPPORTED_STATUSES:
        errors.append(
            f"{spec_path}:{capability['id']}: invalid status {capability['status']}"
        )
    if (
        not isinstance(capability["required_fields"], list)
        or not capability["required_fields"]
    ):
        errors.append(
            f"{spec_path}:{capability['id']}: required_fields must be a non-empty list"
        )
    if not isinstance(capability["graph_surface"], dict):
        errors.append(
            f"{spec_path}:{capability['id']}: graph_surface must be a mapping"
        )
        return errors
    if capability["status"] == "supported":
        graph_surface = capability["graph_surface"]
        if graph_surface.get("kind") == "none":
            errors.append(
                f"{spec_path}:{capability['id']}: supported capability must declare graph surface"
            )
    if capability["status"] in {"partial", "unsupported"}:
        rationale = capability.get("rationale", "").strip()
        if not rationale:
            errors.append(
                f"{spec_path}:{capability['id']}: partial/unsupported capability requires rationale"
            )
    for ref_key in ("unit_test", "integration_test"):
        ref = capability[ref_key]
        if not _test_ref_exists(root, ref):
            errors.append(
                f"{spec_path}:{capability['id']}: {ref_key} must reference a concrete test function {ref}"
            )
    return errors


def _render_graph_surface(surface: dict[str, Any]) -> str:
    """Render a graph surface descriptor as compact Markdown text."""

    kind = surface.get("kind", "none")
    target = surface.get("target")
    if not target:
        return kind
    return f"{kind}:{target}"


def _matrix_status(spec: dict[str, Any], capability_id: str) -> str:
    """Return matrix status symbol for a named code capability."""

    status = _capability_status(spec, capability_id)
    if status is None:
        return "-"
    if status == "supported":
        return "Y"
    return "P"


def _iac_status(spec: dict[str, Any], capability_ids: tuple[str, ...]) -> str:
    """Return matrix status symbol across a set of IaC capability IDs."""

    statuses = [
        _capability_status(spec, capability_id) for capability_id in capability_ids
    ]
    statuses = [status for status in statuses if status is not None]
    if not statuses:
        return "-"
    if "supported" in statuses:
        return "Y"
    return "P"


def _capability_status(spec: dict[str, Any], capability_id: str) -> str | None:
    """Return the status for a capability id, when present."""

    statuses: list[str] = []
    for capability in spec["capabilities"]:
        if (
            capability["id"] == capability_id
            or capability["extracted_bucket"] == capability_id
        ):
            statuses.append(capability["status"])
    if not statuses:
        return None
    if "supported" in statuses:
        return "supported"
    if "partial" in statuses:
        return "partial"
    return "unsupported"


def _coverage_count(spec: dict[str, Any], ref_type: str) -> str:
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


@lru_cache(maxsize=None)
def _parsed_test_file(path: str) -> ast.AST:
    """Return the parsed AST for a test file path."""

    return ast.parse(Path(path).read_text(encoding="utf-8"))


def _test_ref_exists(root: Path, ref: str) -> bool:
    """Return whether a pytest-style ref resolves to a concrete test function."""

    parts = ref.split("::")
    if not parts:
        return False
    path = root / parts[0]
    if not path.exists():
        return False
    if len(parts) == 1:
        return False

    current_nodes: list[ast.stmt] = list(_parsed_test_file(str(path)).body)
    for index, name in enumerate(parts[1:], start=1):
        match = _find_named_node(current_nodes, name)
        if match is None:
            return False
        if index == len(parts) - 1:
            return isinstance(
                match, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and match.name.startswith("test_")
        if not isinstance(match, ast.ClassDef):
            return False
        current_nodes = list(match.body)
    return True


def _find_named_node(nodes: list[ast.stmt], name: str) -> ast.AST | None:
    """Return the class or function node matching ``name``."""

    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
    return None

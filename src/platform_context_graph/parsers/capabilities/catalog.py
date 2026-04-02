"""Public API for parser capability specifications."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from .matrix import render_feature_matrix, render_graph_surface
from .models import AUTO_GENERATED_BANNER, LanguageCapabilitySpec
from .validation import validate_spec


def repo_root(default: Path | None = None) -> Path:
    """Return the repository root used by parser capability helpers."""

    if default is not None:
        return default.resolve()
    return Path(__file__).resolve().parents[4]


def specs_dir(root: Path | None = None) -> Path:
    """Return the directory containing canonical parser capability specs."""

    resolved_root = repo_root(root)
    preferred = (
        resolved_root
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "capabilities"
        / "specs"
    )
    if preferred.exists():
        return preferred
    return (
        resolved_root
        / "src"
        / "platform_context_graph"
        / "tools"
        / "parser_capabilities"
        / "specs"
    )


def load_language_capability_specs(
    root: Path | None = None,
) -> list[LanguageCapabilitySpec]:
    """Load all parser capability specs from YAML files on disk."""

    resolved_root = repo_root(root)
    specs: list[LanguageCapabilitySpec] = []
    for path in sorted(specs_dir(resolved_root).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            data = {}
        data["spec_path"] = path.relative_to(resolved_root).as_posix()
        specs.append(cast(LanguageCapabilitySpec, data))
    return sorted(
        specs,
        key=lambda spec: (
            spec.get("language") is None,
            str(spec.get("language") or spec.get("spec_path", "")),
        ),
    )


def validate_language_capability_specs(root: Path | None = None) -> list[str]:
    """Validate every parser capability spec under the repository root."""

    resolved_root = repo_root(root)
    errors: list[str] = []
    for spec in load_language_capability_specs(resolved_root):
        errors.extend(validate_spec(resolved_root, spec))
    return errors


def render_language_doc(spec: LanguageCapabilitySpec) -> str:
    """Render one parser capability spec into Markdown."""

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
                surface=render_graph_surface(capability["graph_surface"]),
                unit=capability["unit_test"],
                integration=capability["integration_test"],
                rationale=capability.get("rationale", "-"),
            )
        )

    lines.extend(["", "## Known Limitations"])
    for limitation in spec.get("known_limitations", []):
        lines.append(f"- {limitation}")

    return "\n".join(lines) + "\n"


def expected_generated_language_docs(
    root: Path | None = None,
) -> dict[str, str]:
    """Return the generated doc content expected from the current specs."""

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

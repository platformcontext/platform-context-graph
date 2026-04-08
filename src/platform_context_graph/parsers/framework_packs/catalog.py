"""Loader for declarative framework semantic packs."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from .models import FrameworkPackSpec
from .validation import validate_framework_pack_spec


def repo_root(default: Path | None = None) -> Path:
    """Return the repository root used by framework pack helpers."""

    if default is not None:
        return default.resolve()
    return Path(__file__).resolve().parents[4]


def specs_dir(root: Path | None = None) -> Path:
    """Return the directory containing canonical framework pack specs."""

    if root is None:
        return Path(__file__).resolve().parent / "specs"

    resolved_root = repo_root(root)
    return (
        resolved_root
        / "src"
        / "platform_context_graph"
        / "parsers"
        / "framework_packs"
        / "specs"
    )


def load_framework_pack_specs(root: Path | None = None) -> list[FrameworkPackSpec]:
    """Load all framework semantic pack specs from YAML files on disk."""

    resolved_root = repo_root(root) if root is not None else None
    specs: list[FrameworkPackSpec] = []
    for path in sorted(specs_dir(resolved_root).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            data = {}
        if resolved_root is None:
            data["spec_path"] = path.relative_to(path.parents[3]).as_posix()
        else:
            data["spec_path"] = path.relative_to(resolved_root).as_posix()
        specs.append(cast(FrameworkPackSpec, data))
    return sorted(
        specs,
        key=lambda spec: (
            _sort_order(spec.get("compute_order")),
            _sort_order(spec.get("surface_order")),
            str(spec.get("framework", "")),
        ),
    )


def validate_framework_pack_specs(root: Path | None = None) -> list[str]:
    """Validate every framework-pack spec from disk."""

    errors: list[str] = []
    seen_frameworks: dict[str, str] = {}
    for spec in load_framework_pack_specs(root):
        errors.extend(validate_framework_pack_spec(spec))
        framework = spec.get("framework")
        spec_path = str(spec.get("spec_path", "<unknown>"))
        if not isinstance(framework, str) or not framework.strip():
            continue
        previous = seen_frameworks.get(framework)
        if previous is not None:
            errors.append(
                f"{spec_path}: duplicate framework '{framework}' also declared in "
                f"{previous}"
            )
            continue
        seen_frameworks[framework] = spec_path
    return errors


def _sort_order(value: object) -> int:
    """Return a stable integer sort key even for invalid spec values."""

    if isinstance(value, int):
        return value
    return 0

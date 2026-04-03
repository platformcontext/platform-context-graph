"""Built-in dependency and tool-managed directory exclusions."""

from __future__ import annotations

from pathlib import Path
from typing import Final

_DEPENDENCY_ROOTS_BY_ECOSYSTEM: Final[dict[str, tuple[str, ...]]] = {
    "argocd": (),
    "c": (),
    "c_sharp": (),
    "cloudformation": (),
    "cpp": (),
    "crossplane": (),
    "csharp": (),
    "dart": (),
    "elixir": ("deps",),
    "go": ("vendor",),
    "groovy": (),
    "haskell": (),
    "helm": (),
    "java": (),
    "javascript": ("node_modules", "bower_components", "jspm_packages"),
    "json": ("node_modules", "bower_components", "jspm_packages", "vendor"),
    "kotlin": (),
    "kubernetes": (),
    "kustomize": (),
    "perl": (),
    "php": ("vendor",),
    "python": ("site-packages", "dist-packages", "__pypackages__"),
    "ruby": ("vendor/bundle",),
    "rust": (),
    "scala": (),
    "swift": ("Carthage/Checkouts", ".build/checkouts", "Pods"),
    "terraform": (".terraform",),
    "terragrunt": (".terragrunt-cache",),
    "typescript": ("node_modules", "bower_components", "jspm_packages"),
    "typescriptjsx": ("node_modules", "bower_components", "jspm_packages"),
}

_SHARED_TOOL_OUTPUT_ROOTS: Final[tuple[str, ...]] = (
    ".pulumi",
    ".serverless",
    ".aws-sam",
    ".crossplane",
    "cdk.out",
    ".terramate-cache",
)


def dependency_roots_by_ecosystem() -> dict[str, tuple[str, ...]]:
    """Return the built-in dependency-root catalog keyed by supported ecosystem."""

    return dict(_DEPENDENCY_ROOTS_BY_ECOSYSTEM)


def dependency_ignore_enabled(*, get_config_value_fn: object) -> bool:
    """Return whether discovery should exclude dependency and cache directories."""

    value = None
    if callable(get_config_value_fn):
        value = get_config_value_fn("PCG_IGNORE_DEPENDENCY_DIRS")
    return (value or "true").lower() == "true"


def dependency_root_sequences() -> tuple[tuple[str, ...], ...]:
    """Return normalized dependency-root path sequences matched during discovery."""

    roots = set(_SHARED_TOOL_OUTPUT_ROOTS)
    for ecosystem_roots in _DEPENDENCY_ROOTS_BY_ECOSYSTEM.values():
        roots.update(ecosystem_roots)
    return tuple(sorted((_normalize_root(root) for root in roots), key=len))


def is_dependency_path(path: Path | str) -> bool:
    """Return whether a path lives under a built-in dependency or cache root."""

    parts = tuple(part.lower() for part in Path(path).parts if part not in {"", "."})
    return any(
        _contains_sequence(parts, sequence) for sequence in dependency_root_sequences()
    )


def _normalize_root(root: str) -> tuple[str, ...]:
    """Normalize a catalog root entry into lower-cased path parts."""

    return tuple(part.lower() for part in Path(root).parts if part not in {"", "."})


def _contains_sequence(parts: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    """Return whether ``sequence`` appears contiguously in ``parts``."""

    width = len(sequence)
    if width == 0 or len(parts) < width:
        return False
    return any(
        parts[index : index + width] == sequence
        for index in range(len(parts) - width + 1)
    )


__all__ = [
    "dependency_ignore_enabled",
    "dependency_root_sequences",
    "dependency_roots_by_ecosystem",
    "is_dependency_path",
]

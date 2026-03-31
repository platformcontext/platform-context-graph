"""Helpers for loading the local-only api-node-boats e2e manifest."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


@dataclass(frozen=True)
class RepositorySpec:
    """One repository entry from the local e2e manifest."""

    name: str
    root: str
    required: bool
    clone_url: str | None


@dataclass(frozen=True)
class LocalEcosystemManifest:
    """Validated local-only manifest data for the e2e harness."""

    subject_repository: str
    repos: tuple[RepositorySpec, ...]
    bootstrap_assertions: dict[str, Any]
    scan_mutations: tuple[dict[str, Any], ...]
    scan_assertions: dict[str, Any]
    path: Path


def _require_mapping(payload: Any, *, field_name: str) -> dict[str, Any]:
    """Return one mapping field or raise a validation error."""

    if not isinstance(payload, dict):
        raise ValueError(f"{field_name} must be a mapping")
    return payload


def _require_sequence(payload: Any, *, field_name: str) -> list[Any]:
    """Return one sequence field or raise a validation error."""

    if not isinstance(payload, list) or not payload:
        raise ValueError(f"{field_name} must be a non-empty list")
    return payload


def _load_repo_specs(payload: Any) -> tuple[RepositorySpec, ...]:
    """Return validated repository specifications."""

    repo_rows = _require_sequence(payload, field_name="repos")
    repos: list[RepositorySpec] = []
    for index, row in enumerate(repo_rows):
        row_mapping = _require_mapping(row, field_name=f"repos[{index}]")
        name = str(row_mapping.get("name") or "").strip()
        root = str(row_mapping.get("root") or "").strip()
        if not name:
            raise ValueError(f"repos[{index}].name is required")
        if not root:
            raise ValueError(f"repos[{index}].root is required")
        repos.append(
            RepositorySpec(
                name=name,
                root=root,
                required=bool(row_mapping.get("required", True)),
                clone_url=(
                    str(row_mapping.get("clone_url") or "").strip() or None
                ),
            )
        )
    return tuple(repos)


def _load_yaml_payload(path: Path) -> dict[str, Any]:
    """Return the YAML payload using the current interpreter."""

    command = [
        "uv",
        "run",
        "python",
        "-c",
        (
            "import json, pathlib, yaml; "
            "path = pathlib.Path(__import__('sys').argv[1]); "
            "print(json.dumps(yaml.safe_load(path.read_text(encoding='utf-8'))))"
        ),
        str(path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(
            "Could not parse ecosystem manifest YAML.\n"
            f"stderr:\n{completed.stderr.strip()}"
        )
    return _require_mapping(json.loads(completed.stdout), field_name="manifest")


def load_manifest(manifest_path: str | Path) -> LocalEcosystemManifest:
    """Load and validate one local-only api-node-boats ecosystem manifest."""

    path = Path(manifest_path).expanduser().resolve()
    payload = _load_yaml_payload(path)
    subject_repository = str(payload.get("subject_repository") or "").strip()
    if not subject_repository:
        raise ValueError("subject_repository is required")

    bootstrap_assertions = _require_mapping(
        payload.get("bootstrap_assertions"),
        field_name="bootstrap_assertions",
    )
    scan_assertions = _require_mapping(
        payload.get("scan_assertions"),
        field_name="scan_assertions",
    )

    return LocalEcosystemManifest(
        subject_repository=subject_repository,
        repos=_load_repo_specs(payload.get("repos")),
        bootstrap_assertions=bootstrap_assertions,
        scan_mutations=tuple(
            _require_sequence(payload.get("scan_mutations"), field_name="scan_mutations")
        ),
        scan_assertions=scan_assertions,
        path=path,
    )

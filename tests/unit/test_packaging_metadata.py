from __future__ import annotations

from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pytest_is_dev_only_dependency() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())

    runtime_dependencies = pyproject["project"]["dependencies"]
    dev_dependencies = pyproject["project"]["optional-dependencies"]["dev"]

    assert not any(
        dependency.startswith("pytest") for dependency in runtime_dependencies
    )
    assert any(dependency.startswith("pytest") for dependency in dev_dependencies)

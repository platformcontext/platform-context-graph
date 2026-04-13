"""Tests for the Go-owned local indexing runtime bridge."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.cli.helpers import go_index_runtime


def test_resolve_go_bootstrap_index_command_prefers_explicit_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Explicit binary overrides should win over PATH and repo fallbacks."""

    binary_path = tmp_path / "pcg-bootstrap-index"
    binary_path.write_text("")

    monkeypatch.setenv("PCG_BOOTSTRAP_INDEX_BIN", str(binary_path))
    monkeypatch.setattr(go_index_runtime.shutil, "which", lambda _: None)

    command, cwd = go_index_runtime.resolve_go_bootstrap_index_command()

    assert command == [str(binary_path)]
    assert cwd is None


def test_resolve_go_bootstrap_index_command_uses_installed_binary(
    monkeypatch,
) -> None:
    """Installed Go runtime binaries should be preferred when present."""

    monkeypatch.delenv("PCG_BOOTSTRAP_INDEX_BIN", raising=False)
    monkeypatch.setattr(
        go_index_runtime.shutil,
        "which",
        lambda binary: "/usr/local/bin/pcg-bootstrap-index"
        if binary == "pcg-bootstrap-index"
        else None,
    )

    command, cwd = go_index_runtime.resolve_go_bootstrap_index_command()

    assert command == ["/usr/local/bin/pcg-bootstrap-index"]
    assert cwd is None


def test_resolve_go_bootstrap_index_command_falls_back_to_go_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Repo checkouts should be able to launch the Go runtime via ``go run``."""

    go_root = tmp_path / "go"
    bootstrap_root = go_root / "cmd" / "bootstrap-index"
    bootstrap_root.mkdir(parents=True)
    (go_root / "go.mod").write_text("module example.com/test\n")
    (bootstrap_root / "main.go").write_text("package main\n")

    monkeypatch.delenv("PCG_BOOTSTRAP_INDEX_BIN", raising=False)
    monkeypatch.setattr(go_index_runtime.shutil, "which", lambda _: None)
    monkeypatch.setattr(go_index_runtime, "_repo_root", lambda: tmp_path)

    command, cwd = go_index_runtime.resolve_go_bootstrap_index_command()

    assert command == ["go", "run", "./cmd/bootstrap-index"]
    assert cwd == go_root


def test_build_go_bootstrap_index_env_sets_direct_filesystem_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Local repo indexing should launch the Go runtime in direct filesystem mode."""

    root_path = tmp_path / "repo"
    root_path.mkdir()
    app_home = tmp_path / "pcg-home"
    monkeypatch.setenv("PCG_HOME", str(app_home))

    env = go_index_runtime.build_go_bootstrap_index_env(root_path)

    assert env["PCG_REPO_SOURCE_MODE"] == "filesystem"
    assert env["PCG_FILESYSTEM_ROOT"] == str(root_path)
    assert env["PCG_FILESYSTEM_DIRECT"] == "true"
    assert env["PCG_REPOS_DIR"].startswith(str(app_home))
    assert "PCG_REPOSITORY_RULES_JSON" not in env


def test_build_go_bootstrap_index_env_encodes_selected_repositories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Workspace subset indexing should pass exact filesystem-relative rules."""

    workspace = tmp_path / "workspace"
    repo_a = workspace / "platformcontext" / "service-a"
    repo_b = workspace / "platformcontext" / "service-b"
    repo_a.mkdir(parents=True)
    repo_b.mkdir(parents=True)
    monkeypatch.setenv("PCG_HOME", str(tmp_path / "pcg-home"))

    env = go_index_runtime.build_go_bootstrap_index_env(
        workspace,
        selected_repositories=[repo_a, repo_b],
    )

    rules = json.loads(env["PCG_REPOSITORY_RULES_JSON"])
    assert rules == [
        {"kind": "exact", "value": "platformcontext/service-a"},
        {"kind": "exact", "value": "platformcontext/service-b"},
    ]


def test_build_go_bootstrap_index_env_marks_dependency_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Dependency package indexing should carry explicit dependency target metadata."""

    package_root = tmp_path / "node_modules" / "@scope" / "service-lib"
    package_root.mkdir(parents=True)
    monkeypatch.setenv("PCG_HOME", str(tmp_path / "pcg-home"))

    env = go_index_runtime.build_go_bootstrap_index_env(
        package_root,
        is_dependency=True,
        package_name="@scope/service-lib",
        language="typescript",
    )

    assert env["PCG_BOOTSTRAP_IS_DEPENDENCY"] == "true"
    assert env["PCG_BOOTSTRAP_PACKAGE_NAME"] == "@scope/service-lib"
    assert env["PCG_BOOTSTRAP_PACKAGE_LANGUAGE"] == "typescript"

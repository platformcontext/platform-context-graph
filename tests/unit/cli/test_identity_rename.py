from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

from platform_context_graph import paths
from platform_context_graph.cli import main, setup_wizard
from platform_context_graph.versioning import ensure_v_prefix

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_get_app_home_uses_pcg_home_env_var(tmp_path):
    configured_home = tmp_path / "configured-home"

    with patch.dict("os.environ", {"PCG_HOME": str(configured_home)}, clear=True):
        assert paths.get_app_home() == configured_home


def test_get_app_home_defaults_to_platform_context_graph_directory(tmp_path):
    home = tmp_path / "home"
    home.mkdir()

    with patch.object(paths, "Path") as mock_path:
        mock_path.home.return_value = home
        with patch.dict("os.environ", {}, clear=True):
            assert paths.get_app_home() == home / ".platform-context-graph"


def test_get_version_returns_dev_when_distribution_is_missing():
    def fake_pkg_version(package_name: str) -> str:
        if package_name == "platform-context-graph":
            raise PackageNotFoundError
        raise AssertionError(f"unexpected package lookup: {package_name}")

    with patch.object(main, "pkg_version", side_effect=fake_pkg_version):
        assert main.get_version() == "v0.0.0 (dev)"


def test_get_version_adds_v_prefix_for_installed_distribution():
    with patch.object(main, "pkg_version", return_value="0.0.44"):
        assert main.get_version() == "v0.0.44"


def test_ensure_v_prefix_only_strips_existing_prefix_for_version_like_strings():
    assert ensure_v_prefix("V0.0.44") == "v0.0.44"
    assert ensure_v_prefix("Version 0.0.44") == "vVersion 0.0.44"


def test_resolve_cli_command_uses_platform_context_graph_module():
    with (
        patch.object(setup_wizard.shutil, "which", return_value=None),
        patch.object(setup_wizard.sys, "executable", "/usr/bin/python3"),
    ):
        command, args = setup_wizard._resolve_cli_command()

    assert command == "/usr/bin/python3"
    assert args == ["-m", "platform_context_graph", "mcp", "start"]


def test_resolve_cli_command_uses_python_when_pcg_binary_is_missing():
    def fake_which(binary: str) -> str | None:
        if binary == "pcg":
            return None
        return None

    with (
        patch.object(setup_wizard.shutil, "which", side_effect=fake_which),
        patch.object(setup_wizard.sys, "executable", "/usr/bin/python3"),
    ):
        command, args = setup_wizard._resolve_cli_command()

    assert command == "/usr/bin/python3"
    assert args == ["-m", "platform_context_graph", "mcp", "start"]


def test_binary_entrypoint_uses_new_names_only():
    entrypoint = REPO_ROOT / "pcg_entry.py"
    assert entrypoint.exists()

    content = entrypoint.read_text()
    assert "PCG_RUN_FALKOR_WORKER" in content
    assert "platform_context_graph.cli.main" in content
    assert content.count("RUN_FALKOR_WORKER") == 1

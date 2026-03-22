"""Unit tests for visualization helper path resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.cli.helpers import visualization


def test_visualize_helper_uses_packaged_viz_dist_directory(
    monkeypatch, tmp_path: Path
) -> None:
    """Resolve the packaged Playground assets from the package root."""

    package_root = tmp_path / "platform_context_graph"
    (package_root / "cli" / "helpers").mkdir(parents=True)
    dist_dir = package_root / "viz" / "dist"
    dist_dir.mkdir(parents=True)

    db_manager = MagicMock()
    console = MagicMock()
    fake_api = SimpleNamespace(
        _initialize_services=lambda: (db_manager, object(), object()),
        console=console,
    )
    run_server = MagicMock()
    set_db_manager = MagicMock()

    monkeypatch.setattr(
        visualization,
        "__file__",
        str(package_root / "cli" / "helpers" / "visualization.py"),
    )
    monkeypatch.setattr(visualization, "_api", lambda: fake_api)
    monkeypatch.setitem(
        sys.modules,
        "platform_context_graph.viz.server",
        SimpleNamespace(run_server=run_server, set_db_manager=set_db_manager),
    )

    visualization.visualize_helper(repo_path=None, port=8123)

    set_db_manager.assert_called_once_with(db_manager)
    run_server.assert_called_once_with(
        host="127.0.0.1",
        port=8123,
        static_dir=str(dist_dir),
    )
    db_manager.close_driver.assert_called_once()

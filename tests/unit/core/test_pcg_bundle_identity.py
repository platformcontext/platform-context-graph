from __future__ import annotations

import importlib
import sys
from datetime import datetime
from unittest.mock import MagicMock


def test_base_package_name_strips_pcg_extension():
    sys.modules.setdefault("requests", MagicMock())
    registry_commands = importlib.import_module(
        "platform_context_graph.cli.registry_commands"
    )
    assert registry_commands._get_base_package_name("numpy.pcg") == "numpy"


def test_bundle_export_defaults_to_pcg_extension(tmp_path, monkeypatch):
    from platform_context_graph.core.pcg_bundle import PCGBundle

    db_manager = MagicMock()
    db_manager.get_backend_type.return_value = "falkordb"
    bundle = PCGBundle(db_manager)

    monkeypatch.setattr(
        bundle,
        "_extract_metadata",
        lambda repo_path: {"repo": "demo", "pcg_version": bundle.VERSION},
    )
    monkeypatch.setattr(bundle, "_extract_schema", lambda: {})
    monkeypatch.setattr(bundle, "_extract_nodes", lambda output_path, repo_path: 0)
    monkeypatch.setattr(bundle, "_extract_edges", lambda output_path, repo_path: 0)
    monkeypatch.setattr(
        bundle, "_generate_stats", lambda repo_path, node_count, edge_count: {}
    )
    monkeypatch.setattr(
        bundle, "_create_readme", lambda output_path, metadata, stats: None
    )
    monkeypatch.setattr(
        bundle,
        "_create_zip",
        lambda temp_path, output_path: output_path.write_text("bundle"),
    )

    success, _message = bundle.export_to_bundle(tmp_path / "sample-bundle")

    assert success is True
    assert (tmp_path / "sample-bundle.pcg").exists()


def test_bundle_export_serializes_datetime_like_schema_values(tmp_path, monkeypatch):
    from platform_context_graph.core.pcg_bundle import PCGBundle

    db_manager = MagicMock()
    db_manager.get_backend_type.return_value = "neo4j"
    bundle = PCGBundle(db_manager)

    monkeypatch.setattr(
        bundle,
        "_extract_metadata",
        lambda repo_path: {"repo": "demo", "pcg_version": bundle.VERSION},
    )
    monkeypatch.setattr(
        bundle,
        "_extract_schema",
        lambda: {"indexes": [{"createdAt": datetime(2026, 3, 25, 19, 16, 0)}]},
    )
    monkeypatch.setattr(bundle, "_extract_nodes", lambda output_path, repo_path: 0)
    monkeypatch.setattr(bundle, "_extract_edges", lambda output_path, repo_path: 0)
    monkeypatch.setattr(
        bundle, "_generate_stats", lambda repo_path, node_count, edge_count: {}
    )
    monkeypatch.setattr(
        bundle, "_create_readme", lambda output_path, metadata, stats: None
    )
    monkeypatch.setattr(
        bundle,
        "_create_zip",
        lambda temp_path, output_path: output_path.write_text("bundle"),
    )

    success, _message = bundle.export_to_bundle(tmp_path / "sample-datetime-bundle")

    assert success is True
    assert (tmp_path / "sample-datetime-bundle.pcg").exists()

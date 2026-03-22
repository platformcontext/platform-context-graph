"""Tests for checkpoint snapshot persistence."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.indexing.coordinator_models import RepositorySnapshot
from platform_context_graph.indexing.coordinator_storage import _load_snapshot, _save_snapshot


def test_save_snapshot_serializes_nested_path_values(tmp_path, monkeypatch) -> None:
    """Snapshot persistence should normalize nested ``Path`` values to strings."""

    monkeypatch.setattr(
        "platform_context_graph.indexing.coordinator_storage.get_app_home",
        lambda: tmp_path,
    )

    snapshot = RepositorySnapshot(
        repo_path="/tmp/example-repo",
        file_count=1,
        imports_map={"module": ["/tmp/example-repo/src/example.py"]},
        file_data=[
            {
                "path": "/tmp/example-repo/src/example.py",
                "lang": "python",
                "metadata": {
                    "origin": Path("/tmp/example-repo/src/example.py"),
                },
            }
        ],
    )

    _save_snapshot("run-1234", snapshot)

    loaded = _load_snapshot("run-1234", Path(snapshot.repo_path))
    assert loaded is not None
    assert loaded.file_data[0]["metadata"]["origin"] == "/tmp/example-repo/src/example.py"

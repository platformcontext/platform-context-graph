"""Security regression tests for bundle import hardening."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from platform_context_graph.core.pcg_bundle import PCGBundle
from platform_context_graph.core import pcg_bundle_import


class _DummyDBManager:
    """Minimal database manager for import-path tests."""

    def get_backend_type(self) -> str:
        """Report a stable backend type for bundle helpers."""
        return "neo4j"


class _SingleRecordResult:
    """Minimal result wrapper exposing the `single()` interface."""

    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self._payload = payload or {"new_id": "new-node-id"}

    def single(self) -> dict[str, object]:
        """Return one fake record row."""
        return self._payload


class _RecordingSession:
    """Capture queries issued by bundle-import helpers."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def run(self, query: str, **_kwargs) -> _SingleRecordResult:
        """Record one executed query and return a stub result."""
        self.queries.append(query)
        return _SingleRecordResult()


def _write_bundle(
    output_path: Path,
    *,
    extra_entries: dict[str, str] | None = None,
    nodes_content: str = "{}\n",
) -> Path:
    """Create a test bundle with the required files plus optional extras."""

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as bundle_zip:
        bundle_zip.writestr("metadata.json", json.dumps({"pcg_version": "0.1.0"}))
        bundle_zip.writestr("schema.json", "{}")
        bundle_zip.writestr("nodes.jsonl", nodes_content)
        bundle_zip.writestr("edges.jsonl", "{}\n")
        for name, contents in (extra_entries or {}).items():
            bundle_zip.writestr(name, contents)
    return output_path


def _make_bundle_helper() -> PCGBundle:
    """Return a bundle helper with import side effects stubbed out."""

    bundle = PCGBundle(_DummyDBManager())
    bundle._check_existing_repository = lambda *_args, **_kwargs: False  # type: ignore[method-assign]
    bundle._import_schema = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    bundle._import_nodes = lambda *_args, **_kwargs: 1  # type: ignore[method-assign]
    bundle._import_edges = lambda *_args, **_kwargs: 1  # type: ignore[method-assign]
    bundle._clear_graph = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    return bundle


def test_import_from_bundle_rejects_archives_with_too_many_entries(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Archive entry-count caps should fail before extraction or import runs."""

    monkeypatch.setattr(pcg_bundle_import, "MAX_BUNDLE_ARCHIVE_ENTRIES", 4)
    bundle = _make_bundle_helper()
    bundle_path = _write_bundle(
        tmp_path / "too-many-files.pcg",
        extra_entries={"README.md": "bundle", "notes.txt": "notes"},
    )

    success, message = bundle.import_from_bundle(bundle_path)

    assert not success
    assert "has too many entries" in message.lower()


def test_import_from_bundle_rejects_archives_with_excessive_uncompressed_size(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Archive size budgets should reject oversized bundles before extraction."""

    monkeypatch.setattr(pcg_bundle_import, "MAX_BUNDLE_ARCHIVE_BYTES", 32)
    bundle = _make_bundle_helper()
    bundle_path = _write_bundle(
        tmp_path / "too-large.pcg",
        nodes_content="x" * 256,
    )

    success, message = bundle.import_from_bundle(bundle_path)

    assert not success
    assert "maximum extracted size" in message.lower()


def test_import_node_batch_rejects_invalid_label_tokens() -> None:
    """Node imports should reject bundle-provided labels with Cypher syntax."""

    bundle = PCGBundle(_DummyDBManager())
    session = _RecordingSession()

    with pytest.raises(ValueError, match="Invalid Cypher label"):
        bundle._import_node_batch(
            session,
            [(["Repository", "Bad:Label"], {"name": "demo"}, "old-id")],
            {},
        )

    assert session.queries == []


def test_import_edge_batch_rejects_invalid_relationship_types() -> None:
    """Relationship imports should reject unsafe relationship type tokens."""

    bundle = PCGBundle(_DummyDBManager())
    bundle._id_mapping = {"old-a": "new-a", "old-b": "new-b"}
    session = _RecordingSession()

    with pytest.raises(ValueError, match="Invalid Cypher relationship type"):
        bundle._import_edge_batch(
            session,
            [
                {
                    "from": "old-a",
                    "to": "old-b",
                    "type": "REL)-[:PWNED",
                    "properties": {},
                }
            ],
        )

    assert session.queries == []

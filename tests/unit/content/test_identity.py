"""Unit tests for content-entity identity helpers."""

from __future__ import annotations

from platform_context_graph.content.identity import (
    canonical_content_entity_id,
    is_content_entity_id,
)


def test_canonical_content_entity_id_uses_stable_supported_format() -> None:
    """Canonical content IDs should remain stable and match the public regex."""
    entity_id = canonical_content_entity_id(
        repo_id="repository:r_12345678",
        relative_path="src/example.py",
        entity_type="Function",
        entity_name="do_work",
        line_number=42,
    )

    assert entity_id == canonical_content_entity_id(
        repo_id="repository:r_12345678",
        relative_path="src/example.py",
        entity_type="Function",
        entity_name="do_work",
        line_number=42,
    )
    assert is_content_entity_id(entity_id)

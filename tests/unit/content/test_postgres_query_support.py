"""Unit tests for PostgreSQL content-query support helpers."""

from __future__ import annotations

from platform_context_graph.content.postgres_query_support import (
    matches_artifact_type_filter,
    resolve_row_metadata,
)


def test_matches_artifact_type_filter_treats_file_as_plain_source_row() -> None:
    """`file` filters should include rows whose artifact type is still null."""

    assert matches_artifact_type_filter(
        requested_types=["file"],
        resolved_type=None,
    )
    assert not matches_artifact_type_filter(
        requested_types=["dockerfile"],
        resolved_type=None,
    )


def test_resolve_row_metadata_infers_legacy_template_fields() -> None:
    """Legacy rows should derive template metadata from the file content."""

    metadata = resolve_row_metadata(
        relative_path="modules/node/service/templates/default.jinja",
        content='{"name": "${name}", "cpu": ${cpu}}\n',
        row={
            "artifact_type": None,
            "template_dialect": None,
            "iac_relevant": None,
        },
    )

    assert metadata["artifact_type"] == "terraform_template_text"
    assert metadata["template_dialect"] == "terraform_template"
    assert metadata["iac_relevant"] is True

from __future__ import annotations

import pytest

from platform_context_graph.tools.graph_builder_entities import (
    build_entity_merge_statement,
)


def test_build_entity_merge_statement_rejects_invalid_label() -> None:
    with pytest.raises(ValueError, match="Invalid Cypher label"):
        build_entity_merge_statement(
            label="Function:Injected",
            item={"name": "handler", "line_number": 12},
            file_path="/tmp/example.py",
            use_uid_identity=False,
        )


def test_build_entity_merge_statement_rejects_invalid_extra_property_keys() -> None:
    with pytest.raises(ValueError, match="Invalid Cypher property key"):
        build_entity_merge_statement(
            label="Function",
            item={
                "name": "handler",
                "line_number": 12,
                "bad-key": "boom",
            },
            file_path="/tmp/example.py",
            use_uid_identity=False,
        )

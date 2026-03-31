"""Regression coverage for graph schema initialization helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from platform_context_graph.tools.graph_builder_schema import _run_schema_statement


def test_run_schema_statement_retries_neo4j_fulltext_with_modern_syntax() -> None:
    """Legacy Neo4j fulltext procedures should fall back to CREATE FULLTEXT INDEX."""

    session = Mock()
    session.run.side_effect = [
        RuntimeError(
            "Schema statement warning: {neo4j_code: Neo.ClientError.Procedure."
            "ProcedureNotFound} {message: There is no procedure with the name "
            "`db.index.fulltext.createNodeIndex` registered for this database instance.}"
        ),
        None,
    ]

    _run_schema_statement(
        session,
        "CALL db.index.fulltext.createNodeIndex("
        "'code_search_index', ['Function', 'Class', 'Variable'], "
        "['name', 'source', 'docstring'])",
    )

    assert session.run.call_args_list == [
        (
            (
                "CALL db.index.fulltext.createNodeIndex("
                "'code_search_index', ['Function', 'Class', 'Variable'], "
                "['name', 'source', 'docstring'])",
            ),
            {},
        ),
        (
            (
                "CREATE FULLTEXT INDEX code_search_index IF NOT EXISTS "
                "FOR (n:Function|Class|Variable) "
                "ON EACH [n.name, n.source, n.docstring]",
            ),
            {},
        ),
    ]


def test_run_schema_statement_does_not_retry_unrelated_failures() -> None:
    """Non-fulltext schema errors should still surface to the caller."""

    session = SimpleNamespace(run=Mock(side_effect=RuntimeError("constraint failure")))

    try:
        _run_schema_statement(
            session,
            "CREATE CONSTRAINT repository_id IF NOT EXISTS "
            "FOR (r:Repository) REQUIRE r.id IS UNIQUE",
        )
    except RuntimeError as exc:
        assert str(exc) == "constraint failure"
    else:
        raise AssertionError("Expected unrelated schema failures to be re-raised")

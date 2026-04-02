"""Phase 1 import compatibility tests for the graph schema package move."""

from platform_context_graph.graph.schema import (
    create_schema as new_create_schema,
)
from platform_context_graph.graph.schema.builder import (
    _run_schema_statement as new_run_schema_statement,
)
from platform_context_graph.graph.schema.builder import (
    _schema_statements_for_capabilities as new_schema_statements_for_capabilities,
)
from platform_context_graph.tools.graph_builder_schema import (
    _run_schema_statement as legacy_run_schema_statement,
)
from platform_context_graph.tools.graph_builder_schema import (
    _schema_statements_for_capabilities as legacy_schema_statements_for_capabilities,
)
from platform_context_graph.tools.graph_builder_schema import (
    create_schema as legacy_create_schema,
)


def test_graph_schema_moves_to_graph_package() -> None:
    """Expose graph schema helpers from the new graph package."""
    assert new_create_schema.__module__ == "platform_context_graph.graph.schema.builder"


def test_legacy_graph_schema_imports_reexport_new_api() -> None:
    """Keep legacy graph schema imports working during Phase 1."""
    assert legacy_create_schema is new_create_schema
    assert legacy_run_schema_statement is new_run_schema_statement
    assert (
        legacy_schema_statements_for_capabilities
        is new_schema_statements_for_capabilities
    )

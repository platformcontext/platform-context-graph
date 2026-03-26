"""Characterization tests for the `CodeFinder` public interface."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.code_finder import CodeFinder


@pytest.fixture
def code_finder() -> CodeFinder:
    """Create a `CodeFinder` with a mocked database driver.

    Returns:
        A `CodeFinder` instance backed by mocked database objects.
    """
    db_manager = MagicMock()
    db_manager.get_driver.return_value = MagicMock()
    db_manager.get_backend_type.return_value = "neo4j"
    return CodeFinder(db_manager)


def test_find_related_code_ranks_results_by_search_type(
    code_finder: CodeFinder,
) -> None:
    """Test `find_related_code` applies ranking metadata in priority order.

    Args:
        code_finder: Finder under test.
    """
    code_finder.find_by_function_name = MagicMock(
        return_value=[{"name": "f", "is_dependency": False}]
    )
    code_finder.find_by_class_name = MagicMock(
        return_value=[{"name": "c", "is_dependency": True}]
    )
    code_finder.find_by_variable_name = MagicMock(
        return_value=[{"name": "v", "is_dependency": False}]
    )
    code_finder.find_by_content = MagicMock(
        return_value=[{"name": "m", "is_dependency": True}]
    )

    result = code_finder.find_related_code(
        user_query="payment", fuzzy_search=False, edit_distance=2
    )

    assert result["query"] == "payment"
    assert result["total_matches"] == 4
    assert [item["search_type"] for item in result["ranked_results"]] == [
        "function_name",
        "variable_name",
        "class_name",
        "content",
    ]
    assert [item["relevance_score"] for item in result["ranked_results"]] == [
        0.9,
        0.7,
        0.6,
        0.4,
    ]


def test_find_related_code_disables_fuzzy_normalization_for_falkordb() -> None:
    """Test FalkorDB searches use the plain query string instead of Lucene syntax."""
    db_manager = MagicMock()
    db_manager.get_driver.return_value = MagicMock()
    db_manager.get_backend_type.return_value = "falkordb"
    finder = CodeFinder(db_manager)
    finder.find_by_function_name = MagicMock(return_value=[])
    finder.find_by_class_name = MagicMock(return_value=[])
    finder.find_by_variable_name = MagicMock(return_value=[])
    finder.find_by_content = MagicMock(return_value=[])

    result = finder.find_related_code(
        user_query="payment api", fuzzy_search=True, edit_distance=2
    )

    assert result["query"] == "payment api"
    finder.find_by_function_name.assert_called_once_with("payment api", False, None)
    finder.find_by_class_name.assert_called_once_with("payment api", False, None)
    finder.find_by_content.assert_called_once_with("payment api", None)


def test_find_related_code_escapes_lucene_special_characters_for_neo4j() -> None:
    """Test Neo4j fulltext searches escape package-style names before querying."""
    db_manager = MagicMock()
    db_manager.get_driver.return_value = MagicMock()
    db_manager.get_backend_type.return_value = "neo4j"
    finder = CodeFinder(db_manager)
    finder.find_by_function_name = MagicMock(return_value=[])
    finder.find_by_class_name = MagicMock(return_value=[])
    finder.find_by_variable_name = MagicMock(return_value=[])
    finder.find_by_content = MagicMock(return_value=[])

    result = finder.find_related_code(
        user_query="@dmm/lib-node-search", fuzzy_search=True, edit_distance=2
    )

    assert result["query"] == "@dmm\\/lib\\-node\\-search~2"
    finder.find_by_function_name.assert_called_once_with(
        "@dmm\\/lib\\-node\\-search~2", True, None
    )
    finder.find_by_class_name.assert_called_once_with(
        "@dmm\\/lib\\-node\\-search~2", True, None
    )
    finder.find_by_content.assert_called_once_with(
        "@dmm\\/lib\\-node\\-search~2", None
    )


def test_analyze_code_relationships_normalizes_aliases(
    code_finder: CodeFinder,
) -> None:
    """Test alias query types dispatch to the canonical relationship handler."""
    code_finder.who_modifies_variable = MagicMock(
        return_value=[{"container_name": "settings"}]
    )

    result = code_finder.analyze_code_relationships(
        query_type="variable_usage", target="API_KEY", repo_path="/repo"
    )

    assert result == {
        "query_type": "who_modifies",
        "target": "API_KEY",
        "results": [{"container_name": "settings"}],
        "summary": "Found 1 containers that hold variable 'API_KEY'",
    }
    code_finder.who_modifies_variable.assert_called_once_with(
        "API_KEY", repo_path="/repo"
    )


def test_analyze_code_relationships_returns_error_for_invalid_call_chain(
    code_finder: CodeFinder,
) -> None:
    """Test invalid call-chain inputs return the documented error payload."""
    result = code_finder.analyze_code_relationships(
        query_type="call_chain", target="missing-separator"
    )

    assert result == {
        "error": "For call_chain queries, use format 'start_function->end_function'",
        "example": "main->process_data",
    }


def test_list_indexed_repositories_coalesces_missing_dependency_flag() -> None:
    """Repository listing should not warn on graphs missing `is_dependency`."""

    class RecordingSession:
        def __init__(self) -> None:
            self.query: str | None = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query: str, **_kwargs):
            self.query = query
            return type("Result", (), {"data": lambda self: []})()

    session = RecordingSession()
    driver = MagicMock()
    driver.session.return_value = session
    db_manager = MagicMock()
    db_manager.get_driver.return_value = driver
    db_manager.get_backend_type.return_value = "neo4j"

    finder = CodeFinder(db_manager)

    assert finder.list_indexed_repositories() == []
    assert session.query is not None
    assert "coalesce(r[$is_dependency_key], false) as is_dependency" in session.query
    assert "coalesce(r.is_dependency, false) as is_dependency" not in session.query


class RecordingResult:
    def data(self) -> list[dict[str, object]]:
        return []


class RecordingSession:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query: str, **_kwargs):
        self.queries.append(query)
        return RecordingResult()


def _make_recording_finder(*, backend_type: str = "neo4j") -> tuple[CodeFinder, RecordingSession]:
    session = RecordingSession()
    driver = MagicMock()
    driver.session.return_value = session
    db_manager = MagicMock()
    db_manager.get_driver.return_value = driver
    db_manager.get_backend_type.return_value = backend_type
    return CodeFinder(db_manager), session


def test_find_dead_code_uses_dynamic_dependency_properties() -> None:
    """Dead-code analysis should avoid sparse-graph property key warnings."""

    finder, session = _make_recording_finder()

    assert finder.find_dead_code() == {
        "potentially_unused_functions": [],
        "note": "These functions might be unused, but could be entry points, callbacks, or called dynamically",
    }

    assert session.queries
    query = session.queries[-1]
    assert "coalesce(func[$is_dependency_key], false) = false" in query
    assert "coalesce(caller[$is_dependency_key], false) = false" in query
    assert "func.is_dependency = false" not in query
    assert "caller.is_dependency = false" not in query


def test_find_by_variable_name_uses_dynamic_dependency_property() -> None:
    """Variable search should avoid sparse-graph property key warnings."""

    finder, session = _make_recording_finder()

    assert finder.find_by_variable_name("API_KEY") == []

    assert session.queries
    query = session.queries[-1]
    assert "v[$is_dependency_key] as is_dependency" in query
    assert "coalesce(v[$is_dependency_key], false) ASC" in query
    assert "v.is_dependency as is_dependency" not in query


def test_find_module_dependencies_uses_dynamic_import_matching() -> None:
    """Module dependency queries should avoid sparse relationship warnings."""

    finder, session = _make_recording_finder()

    assert finder.find_module_dependencies("requests") == {
        "module_name": "requests",
        "importers": [],
        "imports": [],
    }

    assert len(session.queries) == 2
    importers_query, imports_query = session.queries
    assert "type(imp) = 'IMPORTS'" in importers_query
    assert "file[$is_dependency_key] as file_is_dependency" in importers_query
    assert "[imp:IMPORTS]" not in importers_query
    assert "MATCH (file:File)-[target_rel]->(target_module:Module {name: $module_name})" in imports_query
    assert "WHERE type(target_rel) = 'IMPORTS'" in imports_query
    assert "MATCH (file)-[imp]->(other_module:Module)" in imports_query
    assert "[imp:IMPORTS]" not in imports_query

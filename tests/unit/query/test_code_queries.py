from __future__ import annotations

from unittest.mock import MagicMock

from platform_context_graph.repository_identity import canonical_repository_id
from platform_context_graph.query.code import (
    find_dead_code,
    get_code_relationships,
    get_complexity,
    search_code,
)
from platform_context_graph.mcp.tools.handlers import analysis


def test_search_code_delegates_to_code_finder():
    finder = MagicMock()
    finder.find_related_code.return_value = {"ranked_results": ["a", "b", "c"]}

    result = search_code(finder, query="payment", repo_id="/repo", exact=False, limit=2)

    finder.find_related_code.assert_called_once_with(
        "payment", True, 2, repo_path="/repo"
    )
    assert result == {"ranked_results": ["a", "b"]}


def test_search_code_supports_legacy_edit_distance_override():
    finder = MagicMock()
    finder.find_related_code.return_value = {"ranked_results": ["a"]}

    result = search_code(
        finder,
        query="payment",
        repo_id="/repo",
        exact=False,
        limit=10,
        edit_distance=1,
    )

    finder.find_related_code.assert_called_once_with(
        "payment", True, 1, repo_path="/repo"
    )
    assert result == {"ranked_results": ["a"]}


def test_get_code_relationships_delegates_to_code_finder():
    finder = MagicMock()
    finder.analyze_code_relationships.return_value = {"results": []}

    result = get_code_relationships(
        finder,
        query_type="find_callers",
        target="foo",
        context="src/foo.py",
        repo_id="/repo",
    )

    finder.analyze_code_relationships.assert_called_once_with(
        "find_callers",
        "foo",
        "src/foo.py",
        repo_path="/repo",
    )
    assert result == {"results": []}


def test_get_code_relationships_normalizes_service_friendly_aliases():
    finder = MagicMock()
    finder.analyze_code_relationships.return_value = {"results": []}

    result = get_code_relationships(
        finder,
        query_type="callers",
        target="foo",
        context="src/foo.py",
        repo_id="/repo",
    )

    finder.analyze_code_relationships.assert_called_once_with(
        "find_callers",
        "foo",
        "src/foo.py",
        repo_path="/repo",
    )
    assert result == {"results": []}


def test_find_dead_code_delegates_to_code_finder():
    finder = MagicMock()
    finder.find_dead_code.return_value = {"potentially_unused_functions": []}

    result = find_dead_code(
        finder, repo_path="/repo", exclude_decorated_with=["@app.route"]
    )

    finder.find_dead_code.assert_called_once_with(
        exclude_decorated_with=["@app.route"],
        repo_path="/repo",
    )
    assert result == {"potentially_unused_functions": []}


def test_get_complexity_uses_single_function_lookup():
    finder = MagicMock()
    finder.get_cyclomatic_complexity.return_value = {
        "function_name": "foo",
        "complexity": 7,
    }

    result = get_complexity(
        finder,
        mode="function",
        function_name="foo",
        path="src/foo.py",
        repo_id="/repo",
    )

    finder.get_cyclomatic_complexity.assert_called_once_with(
        "foo", "src/foo.py", repo_path="/repo"
    )
    assert result == {"function_name": "foo", "complexity": 7}


def test_get_complexity_uses_top_complex_functions_mode():
    finder = MagicMock()
    finder.find_most_complex_functions.return_value = [
        {"function_name": "foo", "complexity": 12}
    ]

    result = get_complexity(finder, mode="top", limit=5, repo_id="/repo")

    finder.find_most_complex_functions.assert_called_once_with(5, repo_path="/repo")
    assert result == [{"function_name": "foo", "complexity": 12}]


def test_search_code_resolves_canonical_repository_ids_to_repo_paths():
    class FakeResult:
        def __init__(self, *, records=None):
            self._records = records or []

        def data(self):
            return self._records

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, **_kwargs):
            if "MATCH (r:Repository)" in query:
                return FakeResult(
                    records=[
                        {
                            "name": "payments-api",
                            "path": "/repos/payments-api",
                            "local_path": "/repos/payments-api",
                            "remote_url": "https://github.com/platformcontext/payments-api",
                            "repo_slug": "platformcontext/payments-api",
                            "has_remote": True,
                        }
                    ]
                )
            raise AssertionError(f"unexpected query: {query}")

    finder = MagicMock()
    finder.get_driver.return_value.session.return_value = FakeSession()
    finder.find_related_code.return_value = {"ranked_results": ["a"]}

    result = search_code(
        finder,
        query="payment",
        repo_id=canonical_repository_id(
            remote_url="git@github.com:platformcontext/payments-api.git",
            local_path="/repos/payments-api",
        ),
        exact=False,
        limit=10,
    )

    finder.find_related_code.assert_called_once_with(
        "payment", True, 2, repo_path="/repos/payments-api"
    )
    assert result == {"ranked_results": ["a"]}


def test_get_code_relationships_resolves_canonical_repository_ids_to_repo_paths():
    class FakeResult:
        def __init__(self, *, records=None):
            self._records = records or []

        def data(self):
            return self._records

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, **_kwargs):
            if "MATCH (r:Repository)" in query:
                return FakeResult(
                    records=[
                        {
                            "name": "payments-api",
                            "path": "/repos/payments-api",
                            "local_path": "/repos/payments-api",
                            "remote_url": "https://github.com/platformcontext/payments-api",
                            "repo_slug": "platformcontext/payments-api",
                            "has_remote": True,
                        }
                    ]
                )
            raise AssertionError(f"unexpected query: {query}")

    finder = MagicMock()
    finder.get_driver.return_value.session.return_value = FakeSession()
    finder.analyze_code_relationships.return_value = {"results": []}

    result = get_code_relationships(
        finder,
        query_type="find_callers",
        target="foo",
        context="src/foo.py",
        repo_id=canonical_repository_id(
            remote_url="git@github.com:platformcontext/payments-api.git",
            local_path="/repos/payments-api",
        ),
    )

    finder.analyze_code_relationships.assert_called_once_with(
        "find_callers",
        "foo",
        "src/foo.py",
        repo_path="/repos/payments-api",
    )
    assert result == {"results": []}


def test_get_complexity_resolves_canonical_repository_ids_to_repo_paths():
    class FakeResult:
        def __init__(self, *, records=None):
            self._records = records or []

        def data(self):
            return self._records

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, **_kwargs):
            if "MATCH (r:Repository)" in query:
                return FakeResult(
                    records=[
                        {
                            "name": "payments-api",
                            "path": "/repos/payments-api",
                            "local_path": "/repos/payments-api",
                            "remote_url": "https://github.com/platformcontext/payments-api",
                            "repo_slug": "platformcontext/payments-api",
                            "has_remote": True,
                        }
                    ]
                )
            raise AssertionError(f"unexpected query: {query}")

    finder = MagicMock()
    finder.get_driver.return_value.session.return_value = FakeSession()
    finder.find_most_complex_functions.return_value = [
        {"function_name": "foo", "complexity": 12}
    ]

    result = get_complexity(
        finder,
        mode="top",
        limit=5,
        repo_id=canonical_repository_id(
            remote_url="git@github.com:platformcontext/payments-api.git",
            local_path="/repos/payments-api",
        ),
    )

    finder.find_most_complex_functions.assert_called_once_with(
        5, repo_path="/repos/payments-api"
    )
    assert result == [{"function_name": "foo", "complexity": 12}]


def test_search_code_returns_portable_repo_relative_file_references() -> None:
    class FakeResult:
        def __init__(self, *, records=None):
            self._records = records or []

        def data(self):
            return self._records

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, **_kwargs):
            if "MATCH (r:Repository)" in query:
                return FakeResult(
                    records=[
                        {
                            "name": "payments-api",
                            "path": "/repos/payments-api",
                            "local_path": "/repos/payments-api",
                            "remote_url": "https://github.com/platformcontext/payments-api",
                            "repo_slug": "platformcontext/payments-api",
                            "has_remote": True,
                        }
                    ]
                )
            raise AssertionError(f"unexpected query: {query}")

    finder = MagicMock()
    finder.get_driver.return_value.session.return_value = FakeSession()
    finder.find_related_code.return_value = {
        "ranked_results": [
            {
                "name": "process_payment",
                "path": "/repos/payments-api/src/payments.py",
                "line_number": 17,
            }
        ]
    }

    result = search_code(
        finder,
        query="payment",
        repo_id=canonical_repository_id(
            remote_url="git@github.com:platformcontext/payments-api.git",
            local_path="/repos/payments-api",
        ),
        exact=False,
        limit=10,
    )

    assert result["ranked_results"] == [
        {
            "name": "process_payment",
            "relative_path": "src/payments.py",
            "repo_id": canonical_repository_id(
                remote_url="git@github.com:platformcontext/payments-api.git",
                local_path="/repos/payments-api",
            ),
            "line_number": 17,
            "repo_access": {
                "state": "needs_local_checkout",
                "repo_id": canonical_repository_id(
                    remote_url="git@github.com:platformcontext/payments-api.git",
                    local_path="/repos/payments-api",
                ),
                "repo_slug": "platformcontext/payments-api",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "local_path": "/repos/payments-api",
                "recommended_action": "ask_user_for_local_path",
                "interaction_mode": "conversational",
            },
        }
    ]


def test_analysis_handler_find_code_preserves_legacy_envelope():
    finder = MagicMock()
    finder.find_related_code.return_value = {"ranked_results": []}

    result = analysis.find_code(
        finder,
        query="Payment_API",
        fuzzy_search=True,
        edit_distance=1,
        repo_path="/repo",
    )

    finder.find_related_code.assert_called_once_with(
        "payment api", True, 1, repo_path="/repo"
    )
    assert result == {
        "success": True,
        "query": "payment api",
        "results": {"ranked_results": []},
    }


def test_analysis_handler_relationships_preserve_legacy_envelope():
    finder = MagicMock()
    finder.analyze_code_relationships.return_value = {"results": []}

    result = analysis.analyze_code_relationships(
        finder,
        query_type="find_callers",
        target="foo",
        context="src/foo.py",
        repo_path="/repo",
    )

    finder.analyze_code_relationships.assert_called_once_with(
        "find_callers",
        "foo",
        "src/foo.py",
        repo_path="/repo",
    )
    assert result == {
        "success": True,
        "query_type": "find_callers",
        "target": "foo",
        "context": "src/foo.py",
        "results": {"results": []},
    }

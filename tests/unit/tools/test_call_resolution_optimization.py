"""Unit tests for function-call resolution optimization (Waves 1-3).

Wave 1: Aggregated unresolved reporting via Counter.
Wave 2: Language-compatibility filtering in Cypher queries.
Wave 3: Known-callable pre-filter to skip names absent from the graph.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import platform_context_graph.tools.graph_builder_call_relationships as call_mod
from platform_context_graph.tools.graph_builder_call_relationships import (
    compatible_languages,
    create_all_function_calls,
)
from platform_context_graph.tools.graph_builder_call_batches import (
    contextual_call_batch_queries,
    contextual_call_fallback_batch_query,
    contextual_repo_scoped_batch_query,
    file_level_call_batch_queries,
    file_level_call_fallback_batch_query,
    file_level_repo_scoped_batch_query,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeResult:
    """Minimal Neo4j result stand-in."""

    def __init__(self, row: dict[str, object] | list[dict[str, object]] | None) -> None:
        self._row = row

    def single(self) -> dict[str, object] | None:
        if isinstance(self._row, list):
            return self._row[0] if self._row else None
        return self._row

    def data(self) -> list[dict[str, Any]]:
        if self._row is None:
            return []
        return self._row if isinstance(self._row, list) else [self._row]


class _FakeSession:
    """Records all ``run()`` calls and returns matched row IDs."""

    def __init__(
        self,
        *,
        known_names: list[dict[str, str]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._known_names = known_names or []

    def run(self, query: str, params: dict[str, object] | None = None):
        final_params = params or {}
        self.calls.append((query, final_params))
        if "RETURN DISTINCT n.name AS name" in query:
            return _FakeResult(self._known_names)
        if "rows" in final_params:
            matched_ids = [row["row_id"] for row in final_params["rows"]]
            return _FakeResult({"matched_row_ids": matched_ids})
        return _FakeResult({"created": 1})


class _FamilyAwareFakeSession:
    """Session that returns name+lang for the family-aware query."""

    def __init__(self, names_with_lang: list[dict[str, str]]) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._names_with_lang = names_with_lang

    def run(self, query: str, params=None):
        final_params = params or {}
        self.calls.append((query, final_params))
        if "RETURN DISTINCT n.name AS name, n.lang AS lang" in query:
            return _FakeResult(self._names_with_lang)
        if "RETURN DISTINCT n.name AS name" in query:
            return _FakeResult(self._names_with_lang)
        if "rows" in final_params:
            matched_ids = [row["row_id"] for row in final_params["rows"]]
            return _FakeResult({"matched_row_ids": matched_ids})
        return _FakeResult({"created": 1})


class _FakeSessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __enter__(self) -> _FakeSession:
        return self._session

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSessionContext:
        return _FakeSessionContext(self._session)


# ---------------------------------------------------------------------------
# Wave 2: compatible_languages()
# ---------------------------------------------------------------------------


class TestCompatibleLanguages:
    """Tests for the language-family compatibility helper."""

    def test_none_returns_empty(self) -> None:
        """None language should return an empty list."""
        assert compatible_languages(None) == []

    def test_empty_string_returns_empty(self) -> None:
        """Empty string language should return an empty list."""
        assert compatible_languages("") == []

    def test_javascript_includes_typescript(self) -> None:
        """JavaScript should be cross-compatible with TypeScript."""
        result = compatible_languages("javascript")
        assert "javascript" in result
        assert "typescript" in result

    def test_typescript_includes_javascript(self) -> None:
        """TypeScript should be cross-compatible with JavaScript."""
        result = compatible_languages("typescript")
        assert "typescript" in result
        assert "javascript" in result

    def test_php_returns_self_only(self) -> None:
        """PHP has no family — should only resolve against itself."""
        assert compatible_languages("php") == ["php"]

    def test_python_returns_self_only(self) -> None:
        """Python has no family — should only resolve against itself."""
        assert compatible_languages("python") == ["python"]

    def test_go_returns_self_only(self) -> None:
        """Go has no family — should only resolve against itself."""
        assert compatible_languages("go") == ["go"]

    def test_unknown_language_returns_self(self) -> None:
        """An unrecognized language should resolve only against itself."""
        assert compatible_languages("haskell") == ["haskell"]


# ---------------------------------------------------------------------------
# Wave 2: compatible_langs in call params
# ---------------------------------------------------------------------------


class TestCallParamsIncludeCompatibleLangs:
    """Verify _build_call_params includes compatible_langs."""

    def test_params_carry_compatible_langs_for_python(self) -> None:
        """Python call params should carry compatible_langs=['python']."""
        rows_c, rows_f, _ = call_mod._prepare_call_rows(
            {
                "path": "/tmp/repo/main.py",
                "repo_path": "/tmp/repo",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "helper", "line_number": 10, "args": [], "lang": "python"},
                ],
            },
            {"helper": ["/tmp/repo/helpers.py"]},
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            start_row_id=0,
        )
        all_rows = rows_c + rows_f
        assert len(all_rows) == 1
        assert all_rows[0]["compatible_langs"] == ["python"]

    def test_params_carry_js_ts_family(self) -> None:
        """JavaScript call params should list both JS and TS."""
        rows_c, rows_f, _ = call_mod._prepare_call_rows(
            {
                "path": "/tmp/repo/app.js",
                "repo_path": "/tmp/repo",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {
                        "name": "render",
                        "line_number": 5,
                        "args": [],
                        "lang": "javascript",
                    },
                ],
            },
            {"render": ["/tmp/repo/ui.js"]},
            caller_file_path="/tmp/repo/app.js",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            start_row_id=0,
        )
        all_rows = rows_c + rows_f
        assert len(all_rows) == 1
        langs = all_rows[0]["compatible_langs"]
        assert "javascript" in langs
        assert "typescript" in langs

    def test_params_carry_empty_when_no_lang(self) -> None:
        """When call has no lang, compatible_langs should be empty."""
        rows_c, rows_f, _ = call_mod._prepare_call_rows(
            {
                "path": "/tmp/repo/main.py",
                "repo_path": "/tmp/repo",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "helper", "line_number": 10, "args": []},
                ],
            },
            {"helper": ["/tmp/repo/helpers.py"]},
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            start_row_id=0,
        )
        all_rows = rows_c + rows_f
        assert len(all_rows) == 1
        assert all_rows[0]["compatible_langs"] == []


# ---------------------------------------------------------------------------
# Wave 2: Cypher queries carry language filter
# ---------------------------------------------------------------------------


class TestCypherQueriesHaveLangFilter:
    """All repo-scoped and fallback queries must filter by compatible_langs."""

    def test_contextual_repo_scoped_has_lang_filter(self) -> None:
        """Contextual repo-scoped query should filter by compatible_langs."""
        query = contextual_repo_scoped_batch_query()
        assert (
            "called_function.lang IS NULL OR called_function.lang IN row.compatible_langs"
            in query
        )
        assert (
            "called_class.lang IS NULL OR called_class.lang IN row.compatible_langs"
            in query
        )

    def test_file_level_repo_scoped_has_lang_filter(self) -> None:
        """File-level repo-scoped query should filter by compatible_langs."""
        query = file_level_repo_scoped_batch_query()
        assert (
            "called_function.lang IS NULL OR called_function.lang IN row.compatible_langs"
            in query
        )
        assert (
            "called_class.lang IS NULL OR called_class.lang IN row.compatible_langs"
            in query
        )

    def test_contextual_fallback_has_lang_filter(self) -> None:
        """Contextual fallback query should filter by compatible_langs."""
        query = contextual_call_fallback_batch_query()
        assert "called.lang IS NULL OR called.lang IN row.compatible_langs" in query

    def test_file_level_fallback_has_lang_filter(self) -> None:
        """File-level fallback query should filter by compatible_langs."""
        query = file_level_call_fallback_batch_query()
        assert "called.lang IS NULL OR called.lang IN row.compatible_langs" in query

    def test_contextual_exact_has_lang_filter(self) -> None:
        """Exact match contextual queries must filter by compatible_langs.

        Without this filter, the exact match pass creates cross-language
        false CALLS edges (e.g. PHP → JS) when imports_map resolves a
        name to a file containing a function in a different language.
        """
        for query in contextual_call_batch_queries():
            assert (
                "compatible_langs" in query
            ), "Contextual exact query missing compatible_langs filter"

    def test_file_level_exact_has_lang_filter(self) -> None:
        """Exact match file-level queries must filter by compatible_langs.

        Same rationale as the contextual variant: the exact pass resolves
        by name + path without checking language compatibility, producing
        cross-language false edges.
        """
        for query in file_level_call_batch_queries():
            assert (
                "compatible_langs" in query
            ), "File-level exact query missing compatible_langs filter"


# ---------------------------------------------------------------------------
# Wave 3: known-callable pre-filter
# ---------------------------------------------------------------------------


class TestKnownCallablePreFilter:
    """Tests for _build_known_callable_names and pre-filter logic."""

    def test_build_known_callable_names_queries_both_labels(self) -> None:
        """Should query both Function and Class labels."""
        session = _FakeSession(
            known_names=[{"name": "foo"}, {"name": "Bar"}],
        )
        names = call_mod._build_known_callable_names_flat(session)
        assert "foo" in names
        assert "Bar" in names
        label_queries = [q for q, _ in session.calls if "RETURN DISTINCT n.name" in q]
        assert len(label_queries) == 2

    def test_prefilter_skips_names_not_in_known_set(self) -> None:
        """Calls to names not in known_callable_names should be skipped."""
        counter: Counter[str] = Counter()
        rows_c, rows_f, _ = call_mod._prepare_call_rows(
            {
                "path": "/tmp/repo/main.py",
                "repo_path": "/tmp/repo",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "exists_in_graph", "line_number": 10, "args": []},
                    {"name": "does_not_exist", "line_number": 20, "args": []},
                ],
            },
            {
                "exists_in_graph": ["/tmp/repo/helpers.py"],
                "does_not_exist": ["/tmp/repo/other.py"],
            },
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            start_row_id=0,
            known_callable_names=frozenset({"exists_in_graph"}),
            unresolved_counter=counter,
        )
        all_rows = rows_c + rows_f
        assert len(all_rows) == 1
        assert all_rows[0]["called_name"] == "exists_in_graph"
        assert counter["does_not_exist"] == 1

    def test_prefilter_disabled_when_known_names_is_none(self) -> None:
        """When known_callable_names is None, all calls should pass through."""
        rows_c, rows_f, _ = call_mod._prepare_call_rows(
            {
                "path": "/tmp/repo/main.py",
                "repo_path": "/tmp/repo",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "any_name", "line_number": 10, "args": []},
                ],
            },
            {},
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            start_row_id=0,
            known_callable_names=None,
        )
        all_rows = rows_c + rows_f
        assert len(all_rows) == 1


# ---------------------------------------------------------------------------
# Wave 1: Aggregated unresolved counter
# ---------------------------------------------------------------------------


class TestAggregatedUnresolvedReporting:
    """Tests for Counter-based aggregated unresolved reporting."""

    def test_unresolved_counter_tracks_names(self) -> None:
        """Unresolved calls should increment the Counter, not call warning_logger."""
        warnings: list[str] = []
        counter: Counter[str] = Counter()
        call_mod._prepare_call_rows(
            {
                "path": "/tmp/repo/main.py",
                "repo_path": "/tmp/repo",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "unknown_fn", "line_number": 10, "args": []},
                    {"name": "unknown_fn", "line_number": 20, "args": []},
                    {"name": "other_fn", "line_number": 30, "args": []},
                ],
            },
            {},
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda msg, *_a, **_kw: warnings.append(msg),
            start_row_id=0,
            unresolved_counter=counter,
        )
        # Counter should track names; warning_logger should NOT be called
        assert counter["unknown_fn"] == 2
        assert counter["other_fn"] == 1
        assert len(warnings) == 0

    def test_warning_logger_used_when_no_counter(self) -> None:
        """Without a Counter, unresolved calls should use warning_logger_fn."""
        warnings: list[str] = []
        call_mod._prepare_call_rows(
            {
                "path": "/tmp/repo/main.py",
                "repo_path": "/tmp/repo",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "unknown_fn", "line_number": 10, "args": []},
                ],
            },
            {},
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda msg, *_a, **_kw: warnings.append(msg),
            start_row_id=0,
            unresolved_counter=None,
        )
        assert len(warnings) > 0

    def test_create_all_uses_known_names_and_counter(self) -> None:
        """create_all_function_calls should build known names and aggregate."""
        # The family-aware query returns name+lang pairs.  Calls without
        # a matching lang+name pair should be prefiltered out.
        session = _FamilyAwareFakeSession(
            names_with_lang=[{"name": "helper_one", "lang": "python"}],
        )
        builder = SimpleNamespace(driver=_FakeDriver(session))

        create_all_function_calls(
            builder,
            [
                {
                    "path": "/tmp/repo/a.py",
                    "repo_path": "/tmp/repo",
                    "functions": [],
                    "classes": [],
                    "imports": [],
                    "function_calls": [
                        {
                            "name": "helper_one",
                            "line_number": 10,
                            "args": [],
                            "lang": "python",
                        },
                        {
                            "name": "not_in_graph",
                            "line_number": 20,
                            "args": [],
                            "lang": "python",
                        },
                    ],
                },
            ],
            {"helper_one": ["/tmp/repo/helpers.py"]},
            debug_log_fn=lambda *_a, **_kw: None,
        )

        # The family-aware known-names query should have been executed
        # (2 queries: one for Function, one for Class)
        name_queries = [q for q, _ in session.calls if "RETURN DISTINCT n.name" in q]
        assert len(name_queries) == 2

        # Only helper_one should have reached the batch query
        batch_queries = [(q, p) for q, p in session.calls if "UNWIND $rows AS row" in q]
        for _q, params in batch_queries:
            names = [r["called_name"] for r in params["rows"]]
            assert "not_in_graph" not in names

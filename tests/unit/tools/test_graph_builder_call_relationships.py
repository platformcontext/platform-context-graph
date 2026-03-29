"""Unit tests for batched function-call relationship creation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import builtins as py_builtins

import platform_context_graph.tools.graph_builder_call_relationships as call_relationships
from platform_context_graph.tools.graph_builder_call_relationships import (
    _contextual_call_batch_queries,
    _file_level_call_batch_queries,
    create_all_function_calls,
    create_function_calls,
    safe_run_create,
)


class _FakeResult:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def single(self) -> dict[str, object] | None:
        return self._row


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def run(self, query: str, params: dict[str, object] | None = None):
        final_params = params or {}
        self.calls.append((query, final_params))
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


def test_create_function_calls_batches_file_level_exact_matches() -> None:
    """Resolved file-level calls should be written with batched UNWIND queries."""

    session = _FakeSession()
    builder = SimpleNamespace(
        _safe_run_create=lambda current_session, query, params: safe_run_create(
            current_session, query, params
        )
    )
    file_data = {
        "path": "/tmp/repo/main.py",
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [
            {"name": "helper_one", "line_number": 10, "args": []},
            {"name": "helper_two", "line_number": 20, "args": ["x"]},
        ],
    }
    imports_map = {
        "helper_one": ["/tmp/repo/helpers.py"],
        "helper_two": ["/tmp/repo/helpers.py"],
    }

    create_function_calls(
        builder,
        session,
        file_data,
        imports_map,
        debug_log_fn=lambda *_args, **_kwargs: None,
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert len(session.calls) == 1
    query, params = session.calls[0]
    assert "UNWIND $rows AS row" in query
    assert "COALESCE(called_function, init, called_class)" in query
    assert [row["called_name"] for row in params["rows"]] == [
        "helper_one",
        "helper_two",
    ]


def test_create_function_calls_batches_contextual_exact_matches() -> None:
    """Contextual exact matches should use the merged exact-resolution query."""

    session = _FakeSession()
    builder = SimpleNamespace(
        _safe_run_create=lambda current_session, query, params: safe_run_create(
            current_session, query, params
        )
    )
    file_data = {
        "path": "/tmp/repo/main.py",
        "functions": [{"name": "caller"}],
        "classes": [],
        "imports": [],
        "function_calls": [
            {
                "name": "helper_one",
                "line_number": 10,
                "args": [],
                "context": ["caller", 1, 1],
            }
        ],
    }
    imports_map = {"helper_one": ["/tmp/repo/helpers.py"]}

    create_function_calls(
        builder,
        session,
        file_data,
        imports_map,
        debug_log_fn=lambda *_args, **_kwargs: None,
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert len(session.calls) == 1
    query, params = session.calls[0]
    assert "COALESCE(caller_function, caller_class)" in query
    assert "COALESCE(called_function, init, called_class)" in query
    assert [row["caller_name"] for row in params["rows"]] == ["caller"]


def test_create_all_function_calls_batches_across_files() -> None:
    """Cross-file finalization should buffer rows across files before flushing."""

    session = _FakeSession()
    builder = SimpleNamespace(driver=_FakeDriver(session))
    builder._create_function_calls = lambda current_session, file_data, imports_map: (
        create_function_calls(
            builder,
            current_session,
            file_data,
            imports_map,
            debug_log_fn=lambda *_args, **_kwargs: None,
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda *_args, **_kwargs: None,
        )
    )
    all_file_data = [
        {
            "path": "/tmp/repo/a.py",
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [{"name": "helper_one", "line_number": 10, "args": []}],
        },
        {
            "path": "/tmp/repo/b.py",
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [{"name": "helper_two", "line_number": 20, "args": []}],
        },
    ]
    imports_map = {
        "helper_one": ["/tmp/repo/helpers.py"],
        "helper_two": ["/tmp/repo/helpers.py"],
    }

    create_all_function_calls(
        builder,
        all_file_data,
        imports_map,
        debug_log_fn=lambda *_args, **_kwargs: None,
    )

    assert len(session.calls) == 1
    assert all("UNWIND $rows AS row" in query for query, _params in session.calls)
    assert [len(params["rows"]) for _query, params in session.calls] == [2]


def test_create_all_function_calls_returns_resolution_metrics(
    monkeypatch,
) -> None:
    """Cross-file finalization should surface exact vs fallback metrics."""

    session = _FakeSession()
    builder = SimpleNamespace(driver=_FakeDriver(session))

    monkeypatch.setattr(
        call_relationships,
        "_create_contextual_call_relationships_batched",
        lambda _session, rows: {
            "rows": len(rows),
            "fallback_rows": 1,
            "unmatched_rows": 0,
            "exact_duration_seconds": 2.0,
            "fallback_duration_seconds": 3.0,
        },
    )
    monkeypatch.setattr(
        call_relationships,
        "_create_file_level_call_relationships_batched",
        lambda _session, rows: {
            "rows": len(rows),
            "fallback_rows": 2,
            "unmatched_rows": 1,
            "exact_duration_seconds": 5.0,
            "fallback_duration_seconds": 7.0,
        },
    )

    all_file_data = [
        {
            "path": "/tmp/repo/a.py",
            "functions": [{"name": "caller"}],
            "classes": [],
            "imports": [],
            "function_calls": [
                {
                    "name": "helper_one",
                    "line_number": 10,
                    "args": [],
                    "context": ["caller", 1, 2],
                }
            ],
        },
        {
            "path": "/tmp/repo/b.py",
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [{"name": "helper_two", "line_number": 20, "args": []}],
        },
    ]
    imports_map = {
        "helper_one": ["/tmp/repo/helpers.py"],
        "helper_two": ["/tmp/repo/helpers.py"],
    }

    metrics = create_all_function_calls(
        builder,
        all_file_data,
        imports_map,
        debug_log_fn=lambda *_args, **_kwargs: None,
    )

    assert metrics == {
        "contextual_rows": 1,
        "contextual_fallback_rows": 1,
        "contextual_unmatched_rows": 0,
        "contextual_exact_duration_seconds": 2.0,
        "contextual_fallback_duration_seconds": 3.0,
        "file_level_rows": 1,
        "file_level_fallback_rows": 2,
        "file_level_unmatched_rows": 1,
        "file_level_exact_duration_seconds": 5.0,
        "file_level_fallback_duration_seconds": 7.0,
        "exact_duration_seconds": 7.0,
        "fallback_duration_seconds": 10.0,
        "total_duration_seconds": 17.0,
    }
    assert builder._last_call_relationship_metrics == metrics


def test_create_all_function_calls_reports_per_file_progress() -> None:
    """Cross-file call linking should heartbeat once per processed file."""

    session = _FakeSession()
    builder = SimpleNamespace(driver=_FakeDriver(session))
    progress_updates: list[dict[str, object]] = []

    create_all_function_calls(
        builder,
        [
            {
                "path": "/tmp/repo/a.php",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [],
            },
            {
                "path": "/tmp/repo/b.php",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [],
            },
        ],
        {},
        debug_log_fn=lambda *_args, **_kwargs: None,
        progress_callback=lambda **kwargs: progress_updates.append(kwargs),
    )

    assert progress_updates == [
        {
            "current_file": str(Path("/tmp/repo/a.php").resolve()),
            "processed_files": 1,
            "total_files": 2,
        },
        {
            "current_file": str(Path("/tmp/repo/b.php").resolve()),
            "processed_files": 2,
            "total_files": 2,
        },
    ]


def test_run_call_batch_query_chunks_large_row_sets(monkeypatch) -> None:
    """Large row sets should be split into multiple Neo4j batch queries."""

    monkeypatch.setattr(call_relationships, "_CALL_RELATIONSHIP_BATCH_SIZE", 1)
    session = _FakeSession()
    rows = [
        {
            "row_id": 0,
            "caller_file_path": "/tmp/repo/a.py",
            "called_name": "helper_one",
            "called_file_path": "/tmp/repo/helpers.py",
            "line_number": 10,
            "args": [],
            "full_call_name": "helper_one",
        },
        {
            "row_id": 1,
            "caller_file_path": "/tmp/repo/b.py",
            "called_name": "helper_two",
            "called_file_path": "/tmp/repo/helpers.py",
            "line_number": 20,
            "args": [],
            "full_call_name": "helper_two",
        },
    ]

    remaining_rows = call_relationships._run_call_batch_query(
        session,
        """
        UNWIND $rows AS row
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
        """,
        rows,
    )

    assert remaining_rows == []
    assert len(session.calls) == 2


def test_filter_fallback_candidate_rows_skips_low_signal_javascript_calls() -> None:
    """Global fallback should skip ambiguous minified JavaScript names."""

    rows = [
        {
            "row_id": 1,
            "called_name": "S",
            "full_call_name": 'S("token")',
            "lang": "javascript",
            "caller_file_path": "/tmp/repo/vendor.min.js",
        },
        {
            "row_id": 2,
            "called_name": "createElement",
            "full_call_name": 'document.createElement("div")',
            "lang": "javascript",
            "caller_file_path": "/tmp/repo/vendor.min.js",
        },
        {
            "row_id": 3,
            "called_name": "registerStreamLogger",
            "full_call_name": "registerStreamLogger",
            "lang": "php",
            "caller_file_path": "/tmp/repo/CKFinder.php",
        },
    ]

    filtered = call_relationships._filter_fallback_candidate_rows(rows)

    assert [row["row_id"] for row in filtered] == [3]


def test_filter_fallback_candidate_rows_skips_known_php_builtins() -> None:
    """Global fallback should skip PHP builtins that can never resolve in graph."""

    rows = [
        {
            "row_id": 1,
            "called_name": "isset",
            "full_call_name": "isset",
            "lang": "php",
            "caller_file_path": "/tmp/repo/file.php",
        },
        {
            "row_id": 2,
            "called_name": "array_merge",
            "full_call_name": "array_merge",
            "lang": "php",
            "caller_file_path": "/tmp/repo/file.php",
        },
        {
            "row_id": 3,
            "called_name": "hydrateOrder",
            "full_call_name": "hydrateOrder",
            "lang": "php",
            "caller_file_path": "/tmp/repo/file.php",
        },
    ]

    filtered = call_relationships._filter_fallback_candidate_rows(rows)

    assert [row["row_id"] for row in filtered] == [3]


def test_prepare_call_rows_handles_module_form_builtins_without_type_error(
    monkeypatch,
) -> None:
    """Builtin skipping should not depend on `__builtins__` being a dict."""

    monkeypatch.setattr(call_relationships, "__builtins__", py_builtins)

    contextual_rows, file_level_rows, next_row_id = (
        call_relationships._prepare_call_rows(
            {
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "print", "line_number": 1},
                    {"name": "helper", "line_number": 2},
                ],
            },
            {"helper": ["/tmp/repo/helpers.py"]},
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: "false",
            warning_logger_fn=lambda *_args, **_kwargs: None,
            start_row_id=1,
        )
    )

    resolved_rows = contextual_rows + file_level_rows
    assert len(resolved_rows) == 1
    assert resolved_rows[0]["called_name"] == "helper"
    assert next_row_id == 2


def test_create_all_function_calls_skips_minified_files() -> None:
    """CALLS finalization skips .min.js files to avoid expensive queries on minified bundles."""

    session = _FakeSession()
    builder = SimpleNamespace(driver=_FakeDriver(session))

    create_all_function_calls(
        builder,
        [
            {
                "path": "/tmp/repo/static/vendor/jquery-ui-1.10.4.min.js",
                "lang": "javascript",
                "functions": [{"name": "a"}],
                "classes": [],
                "imports": [],
                "function_calls": [{"name": "call", "line_number": 10, "args": []}],
            },
            {
                "path": "/tmp/repo/app.js",
                "lang": "javascript",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "renderDashboard", "line_number": 20, "args": []}
                ],
            },
        ],
        {"renderDashboard": ["/tmp/repo/helpers.js"]},
        debug_log_fn=lambda *_args, **_kwargs: None,
    )

    assert len(session.calls) == 1
    _query, params = session.calls[0]
    # .min.js files are skipped during call resolution to avoid
    # expensive queries on minified bundles with thousands of
    # single-letter function calls.
    assert [row["caller_file_path"] for row in params["rows"]] == [
        str(Path("/tmp/repo/app.js").resolve()),
    ]


def test_create_all_function_calls_does_not_report_vendored_skip_metrics() -> None:
    """Vendored skip metrics should disappear once exclusion moves to discovery."""

    session = _FakeSession()
    builder = SimpleNamespace(driver=_FakeDriver(session))

    metrics = create_all_function_calls(
        builder,
        [
            {
                "path": "/tmp/repo/vendor/pkg/file.php",
                "lang": "php",
                "functions": [{"name": "vendoredFn"}],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "dependencyCall", "line_number": 5, "args": []}
                ],
            },
            {
                "path": "/tmp/repo/app.js",
                "lang": "javascript",
                "functions": [],
                "classes": [],
                "imports": [],
                "function_calls": [
                    {"name": "renderDashboard", "line_number": 20, "args": []}
                ],
            },
        ],
        {"renderDashboard": ["/tmp/repo/helpers.js"]},
        debug_log_fn=lambda *_args, **_kwargs: None,
    )

    assert "skipped_vendored_files" not in metrics
    assert "skipped_vendored_calls" not in metrics
    assert "skipped_vendored_files" not in builder._last_call_relationship_metrics


def test_contextual_exact_query_preserves_rows_without_constructor_match() -> None:
    """Exact contextual resolution should not filter out null init rows."""

    query = _contextual_call_batch_queries()[0]

    assert 'WHERE init.name IN ["__init__", "constructor"]' not in query
    assert (
        'CASE WHEN init.name IN ["__init__", "constructor"] THEN init END AS init'
        in query
    )


def test_file_level_exact_query_preserves_rows_without_constructor_match() -> None:
    """Exact file-level resolution should not filter out null init rows."""

    query = _file_level_call_batch_queries()[0]

    assert 'WHERE init.name IN ["__init__", "constructor"]' not in query
    assert (
        'CASE WHEN init.name IN ["__init__", "constructor"] THEN init END AS init'
        in query
    )

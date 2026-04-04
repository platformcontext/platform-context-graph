"""Unit tests for batched function-call relationship creation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import builtins as py_builtins

import platform_context_graph.graph.persistence.calls as call_relationships
import platform_context_graph.graph.persistence.call_row_prep as call_row_prep
from platform_context_graph.graph.persistence.calls import (
    _contextual_call_batch_queries,
    _contextual_repo_scoped_batch_query,
    _file_level_call_batch_queries,
    _file_level_repo_scoped_batch_query,
    create_all_function_calls,
    create_function_calls,
    safe_run_create,
)


class _FakeResult:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def single(self) -> dict[str, object] | None:
        return self._row

    def data(self) -> list[dict[str, object]]:
        if self._row is None:
            return []
        return self._row if isinstance(self._row, list) else [self._row]


class _FakeSession:
    def __init__(
        self,
        *,
        known_names: list[dict[str, str]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        # When no known_names supplied, return a broad set so the
        # known-callable pre-filter does not interfere with existing tests.
        self._known_names = (
            known_names
            if known_names is not None
            else [
                {"name": n}
                for n in (
                    "helper_one",
                    "helper_two",
                    "helper",
                    "process",
                    "renderDashboard",
                    "dependencyCall",
                    "vendoredFn",
                    "call",
                )
            ]
        )

    def run(self, query: str, params: dict[str, object] | None = None):
        final_params = params or {}
        self.calls.append((query, final_params))
        if "RETURN DISTINCT n.name" in query:
            return _FakeResult(self._known_names)
        if "rows" in final_params:
            matched_ids = [row["row_id"] for row in final_params["rows"]]
            return _FakeResult({"matched_row_ids": matched_ids})
        return _FakeResult({"created": 1})


class _IterableOnlyResult:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def data(self) -> list[dict[str, str]]:
        raise AssertionError("data() should not be called for name scans")


class _IterableOnlySession:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, object]]] = []

    def run(self, query: str, params: dict[str, object] | None = None):
        self.calls.append((query, params or {}))
        return _IterableOnlyResult(self.rows)


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

    # 2 known-name queries (Function + Class) + 1 UNWIND batch query
    unwind_calls = [(q, p) for q, p in session.calls if "UNWIND $rows AS row" in q]
    assert len(unwind_calls) == 1
    assert [len(params["rows"]) for _query, params in unwind_calls] == [2]


def test_build_known_callable_names_by_family_iterates_rows_lazily() -> None:
    """Known-name scans should not require eager `.data()` materialization."""

    session = _IterableOnlySession(
        rows=[
            {"name": "render", "lang": "javascript"},
            {"name": "setup", "lang": "typescript"},
        ]
    )

    result = call_relationships._build_known_callable_names_by_family(session)

    assert "render" in result["javascript"]
    assert "setup" in result["typescript"]
    assert len(session.calls) == 2


def test_prepare_call_rows_stops_after_max_calls_per_file(monkeypatch) -> None:
    """Per-file call caps should stop row preparation early."""

    resolve_calls = 0

    def _fake_resolve_call_target(*_args, **_kwargs):
        nonlocal resolve_calls
        resolve_calls += 1
        return "/tmp/repo/main.py"

    monkeypatch.setattr(
        call_row_prep,
        "_resolve_call_target",
        _fake_resolve_call_target,
    )

    file_data = {
        "path": "/tmp/repo/main.py",
        "repo_path": "/tmp/repo",
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [
            {"name": f"call_{index}", "line_number": index, "args": []}
            for index in range(20)
        ],
    }

    contextual_rows, file_level_rows, next_row_id = (
        call_relationships._prepare_call_rows(
            file_data,
            {},
            caller_file_path="/tmp/repo/main.py",
            get_config_value_fn=lambda _key: None,
            warning_logger_fn=lambda *_args, **_kwargs: None,
            start_row_id=0,
            max_calls_per_file=5,
        )
    )

    assert resolve_calls == 5
    assert len(contextual_rows) + len(file_level_rows) == 5
    assert next_row_id == 5


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
            "repo_scoped_duration_seconds": 0.5,
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
            "repo_scoped_duration_seconds": 1.0,
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
        "contextual_repo_scoped_duration_seconds": 0.5,
        "contextual_fallback_duration_seconds": 3.0,
        "file_level_rows": 1,
        "file_level_fallback_rows": 2,
        "file_level_unmatched_rows": 1,
        "file_level_exact_duration_seconds": 5.0,
        "file_level_repo_scoped_duration_seconds": 1.0,
        "file_level_fallback_duration_seconds": 7.0,
        "exact_duration_seconds": 7.0,
        "repo_scoped_duration_seconds": 1.5,
        "fallback_duration_seconds": 10.0,
        "total_duration_seconds": 18.5,
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

    # 2 known-name queries (Function + Class) + 1 UNWIND batch query
    unwind_calls = [(q, p) for q, p in session.calls if "UNWIND $rows AS row" in q]
    assert len(unwind_calls) == 1
    _query, params = unwind_calls[0]
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


def test_repo_scoped_queries_restrict_match_to_repo_path() -> None:
    """Repo-scoped queries should filter called functions by repo path prefix."""

    contextual_query = _contextual_repo_scoped_batch_query()
    file_level_query = _file_level_repo_scoped_batch_query()

    assert "STARTS WITH row.repo_path" in contextual_query
    assert "STARTS WITH row.repo_path" in file_level_query
    assert "COALESCE(called_function, init, called_class)" in contextual_query
    assert "COALESCE(called_function, init, called_class)" in file_level_query


def test_prepare_call_rows_includes_repo_path_in_rows() -> None:
    """Prepared rows should carry repo_path for repo-scoped resolution."""

    contextual_rows, file_level_rows, _ = call_relationships._prepare_call_rows(
        {
            "path": "/tmp/repo-a/main.py",
            "repo_path": "/tmp/repo-a",
            "functions": [{"name": "caller"}],
            "classes": [],
            "imports": [],
            "function_calls": [
                {
                    "name": "process",
                    "line_number": 10,
                    "args": [],
                    "context": ["caller", 1, 1],
                },
                {"name": "transform", "line_number": 20, "args": []},
            ],
        },
        {},
        caller_file_path="/tmp/repo-a/main.py",
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        start_row_id=0,
    )

    all_rows = contextual_rows + file_level_rows
    assert len(all_rows) == 2
    assert all(row["repo_path"] == "/tmp/repo-a" for row in all_rows)


def test_repo_scope_prevents_cross_repo_call_resolution(monkeypatch) -> None:
    """With scope=repo, calls should not resolve to functions in other repos."""

    monkeypatch.setenv("PCG_CALL_RESOLUTION_SCOPE", "repo")

    # _RepoAwareSession: exact queries (name+path) never match because the
    # call is unresolved (called_file_path == caller_file_path, no function
    # there).  The repo-scoped query would only match functions whose path
    # starts with the caller's repo_path.  We simulate this: only rows whose
    # repo_path matches the called function's repo resolve.
    class _RepoAwareSession:
        """Session that matches only when repo_path constraint is satisfied."""

        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def run(self, query: str, params=None):
            final_params = params or {}
            self.calls.append((query, final_params))
            if "RETURN DISTINCT n.name" in query:
                return _FakeResult([{"name": "process"}])
            rows = final_params.get("rows", [])
            if "STARTS WITH row.repo_path" in query:
                # Simulate: the only function named 'process' lives in
                # /tmp/repo-b, so repo-scoped match from repo-a fails.
                matched = [
                    r["row_id"]
                    for r in rows
                    if "/tmp/repo-b".startswith(r.get("repo_path", ""))
                ]
                return _FakeResult({"matched_row_ids": matched})
            if "called_file_path" in query and "STARTS WITH" not in query:
                # Exact match: never resolves for unresolved calls
                return _FakeResult({"matched_row_ids": []})
            matched = [r["row_id"] for r in rows]
            return _FakeResult({"matched_row_ids": matched})

    session = _RepoAwareSession()
    builder = SimpleNamespace(driver=_FakeDriver(session))

    all_file_data = [
        {
            "path": "/tmp/repo-a/main.py",
            "repo_path": "/tmp/repo-a",
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [
                {"name": "process", "line_number": 10, "args": []},
            ],
        },
    ]
    # No imports map entry -- the call is unresolved
    imports_map: dict = {}

    metrics = create_all_function_calls(
        builder,
        all_file_data,
        imports_map,
        debug_log_fn=lambda *_args, **_kwargs: None,
    )

    # The call should remain unresolved (NOT matched) because 'process'
    # only exists in repo-b and scope=repo restricts to repo-a.
    repo_scoped_queries = [
        (q, p) for q, p in session.calls if "STARTS WITH row.repo_path" in q
    ]
    assert len(repo_scoped_queries) > 0, "Repo-scoped query should have been executed"
    for _query, params in repo_scoped_queries:
        for row in params.get("rows", []):
            assert row["repo_path"] == "/tmp/repo-a"

    # With scope=repo the unresolved count should be > 0 since
    # 'process' is not in repo-a
    assert metrics["file_level_unmatched_rows"] > 0 or (
        metrics["contextual_unmatched_rows"] > 0
    )


def test_global_scope_skips_repo_scoped_query(monkeypatch) -> None:
    """With scope=global, repo-scoped queries should not be injected."""

    monkeypatch.setenv("PCG_CALL_RESOLUTION_SCOPE", "global")

    session = _FakeSession()
    builder = SimpleNamespace(driver=_FakeDriver(session))

    all_file_data = [
        {
            "path": "/tmp/repo-a/main.py",
            "repo_path": "/tmp/repo-a",
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [
                {"name": "helper_one", "line_number": 10, "args": []},
            ],
        },
    ]
    imports_map = {"helper_one": ["/tmp/repo-a/helpers.py"]}

    create_all_function_calls(
        builder,
        all_file_data,
        imports_map,
        debug_log_fn=lambda *_args, **_kwargs: None,
    )

    repo_scoped_queries = [
        q for q, _p in session.calls if "STARTS WITH row.repo_path" in q
    ]
    assert (
        len(repo_scoped_queries) == 0
    ), "Repo-scoped query should NOT run when scope=global"


# ---------------------------------------------------------------------------
# Fix 1: Family-aware known-callable filter
# ---------------------------------------------------------------------------


class _FamilyAwareSession:
    """Fake session that returns Function/Class names WITH lang property."""

    def __init__(self, names_with_lang: list[dict[str, str]]) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._names_with_lang = names_with_lang

    def run(self, query: str, params=None):
        final_params = params or {}
        self.calls.append((query, final_params))
        if "RETURN DISTINCT n.name AS name, n.lang AS lang" in query:
            return _FakeResult(self._names_with_lang)
        if "rows" in final_params:
            matched_ids = [row["row_id"] for row in final_params["rows"]]
            return _FakeResult({"matched_row_ids": matched_ids})
        return _FakeResult({"created": 1})


def test_build_known_callable_names_by_family_groups_by_language() -> None:
    """JS and TS names should be merged into the same family set; PHP stays separate."""

    session = _FamilyAwareSession(
        names_with_lang=[
            {"name": "render", "lang": "javascript"},
            {"name": "setup", "lang": "typescript"},
            {"name": "fetchBoats", "lang": "php"},
            {"name": "shared", "lang": "javascript"},
        ]
    )

    result = call_relationships._build_known_callable_names_by_family(session)

    # JS and TS share the js_family, so both should see all three names
    assert "render" in result["javascript"]
    assert "setup" in result["javascript"]
    assert "shared" in result["javascript"]
    assert "render" in result["typescript"]
    assert "setup" in result["typescript"]
    assert "shared" in result["typescript"]

    # PHP is its own family
    assert "fetchBoats" in result["php"]
    assert "render" not in result["php"]
    assert "setup" not in result["php"]


def test_family_aware_prefilter_drops_cross_family_names() -> None:
    """A PHP call to a name that only exists as JS callable should be filtered out."""

    from collections import Counter

    unresolved = Counter()
    # Only JS callables exist -- no PHP callables at all
    known_by_family = {
        "javascript": frozenset({"render", "setup"}),
        "typescript": frozenset({"render", "setup"}),
    }

    file_data = {
        "path": "/tmp/repo/file.php",
        "repo_path": "/tmp/repo",
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [
            {"name": "render", "line_number": 10, "args": [], "lang": "php"},
        ],
    }

    contextual_rows, file_level_rows, _ = call_relationships._prepare_call_rows(
        file_data,
        {},
        caller_file_path="/tmp/repo/file.php",
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        start_row_id=0,
        known_callable_names_by_family=known_by_family,
        unresolved_counter=unresolved,
    )

    # The call should have been filtered -- render is JS-only, caller is PHP
    assert len(contextual_rows) == 0
    assert len(file_level_rows) == 0
    assert unresolved["render"] == 1


def test_family_aware_prefilter_allows_same_family_names() -> None:
    """A JS call to a name that exists as TS callable should pass the filter."""

    from collections import Counter

    unresolved = Counter()
    known_by_family = {
        "javascript": frozenset({"render", "setup"}),
        "typescript": frozenset({"render", "setup"}),
    }

    file_data = {
        "path": "/tmp/repo/app.js",
        "repo_path": "/tmp/repo",
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [
            {"name": "render", "line_number": 5, "args": [], "lang": "javascript"},
        ],
    }

    contextual_rows, file_level_rows, _ = call_relationships._prepare_call_rows(
        file_data,
        {},
        caller_file_path="/tmp/repo/app.js",
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        start_row_id=0,
        known_callable_names_by_family=known_by_family,
        unresolved_counter=unresolved,
    )

    # The call should pass -- render exists in the JS family
    all_rows = contextual_rows + file_level_rows
    assert len(all_rows) == 1
    assert all_rows[0]["called_name"] == "render"


def test_family_aware_prefilter_allows_when_lang_is_none() -> None:
    """Calls without a lang property should always pass the prefilter."""

    from collections import Counter

    unresolved = Counter()
    known_by_family = {
        "javascript": frozenset({"render"}),
    }

    file_data = {
        "path": "/tmp/repo/unknown.txt",
        "repo_path": "/tmp/repo",
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [
            # No lang on the call
            {"name": "render", "line_number": 1, "args": []},
        ],
    }

    contextual_rows, file_level_rows, _ = call_relationships._prepare_call_rows(
        file_data,
        {},
        caller_file_path="/tmp/repo/unknown.txt",
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        start_row_id=0,
        known_callable_names_by_family=known_by_family,
        unresolved_counter=unresolved,
    )

    # No lang => should not be filtered
    all_rows = contextual_rows + file_level_rows
    assert len(all_rows) == 1
    assert all_rows[0]["called_name"] == "render"


# ---------------------------------------------------------------------------
# Fix 3: Enhanced aggregated reporting
# ---------------------------------------------------------------------------


def test_unresolved_by_lang_counter() -> None:
    """Per-language unresolved tracking should tally by caller language."""

    from collections import Counter

    unresolved = Counter()
    prefiltered = Counter()
    # Empty callable set for PHP means all PHP calls get prefiltered
    known_by_family = {
        "javascript": frozenset({"render"}),
        "typescript": frozenset({"render"}),
    }

    file_data = {
        "path": "/tmp/repo/file.php",
        "repo_path": "/tmp/repo",
        "functions": [],
        "classes": [],
        "imports": [],
        "function_calls": [
            {"name": "someFunc", "line_number": 10, "args": [], "lang": "php"},
            {"name": "anotherFunc", "line_number": 20, "args": [], "lang": "php"},
        ],
    }

    call_relationships._prepare_call_rows(
        file_data,
        {},
        caller_file_path="/tmp/repo/file.php",
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        start_row_id=0,
        known_callable_names_by_family=known_by_family,
        unresolved_counter=unresolved,
        prefiltered_counter=prefiltered,
    )

    # Both PHP calls should be prefiltered (not in PHP family callable set)
    assert prefiltered["php"] == 2


# ---------------------------------------------------------------------------
# Fix 4: Class-aware resolution guardrails
# ---------------------------------------------------------------------------


def test_max_calls_for_repo_class() -> None:
    """Verify class-aware caps return correct values for each class."""

    max_fn = call_relationships.max_calls_for_repo_class

    assert max_fn("small") == 100
    assert max_fn("medium") == 50
    assert max_fn("large") == 25
    assert max_fn("xlarge") == 15
    assert max_fn("dangerous") == 5
    assert max_fn(None) == call_relationships._MAX_CALLS_PER_FILE
    assert max_fn("unknown") == call_relationships._MAX_CALLS_PER_FILE


def test_adaptive_resolution_guardrails_enabled(monkeypatch) -> None:
    """When env var is true, class-aware cap should be used instead of default."""

    monkeypatch.setenv("PCG_ADAPTIVE_RESOLUTION_GUARDRAILS_ENABLED", "true")

    session = _FamilyAwareSession(
        names_with_lang=[
            {"name": "helper_one", "lang": "python"},
            {"name": "helper_two", "lang": "python"},
        ]
    )
    builder = SimpleNamespace(driver=_FakeDriver(session))

    # Create many calls to exceed the 'large' cap of 25
    many_calls = [
        {"name": "helper_one", "line_number": i, "args": [], "lang": "python"}
        for i in range(60)
    ]

    all_file_data = [
        {
            "path": "/tmp/repo/big.py",
            "repo_path": "/tmp/repo",
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": many_calls,
        },
    ]
    imports_map = {"helper_one": ["/tmp/repo/helpers.py"]}

    metrics = create_all_function_calls(
        builder,
        all_file_data,
        imports_map,
        debug_log_fn=lambda *_args, **_kwargs: None,
        repo_class="large",
    )

    # With repo_class="large", cap is 25. Verify total rows processed <= 25.
    total_rows = metrics.get("contextual_rows", 0) + metrics.get("file_level_rows", 0)
    assert total_rows <= 25

"""Unit tests for batched function-call relationship creation."""

from __future__ import annotations

from types import SimpleNamespace

import platform_context_graph.tools.graph_builder_call_relationships as call_relationships
from platform_context_graph.tools.graph_builder_call_relationships import (
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
    """Cross-file finalization should batch rows across the whole run."""

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
    query, params = session.calls[0]
    assert "UNWIND $rows AS row" in query
    assert len(params["rows"]) == 2


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

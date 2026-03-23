from __future__ import annotations

from datetime import datetime, timezone

from platform_context_graph.query import status as status_queries


class _Store:
    enabled = True

    def __init__(self, payload):
        self._payload = payload

    def get_runtime_status(self, *, ingester: str):
        return self._payload.get(ingester)


def test_get_ingester_status_normalizes_datetime_fields(
    monkeypatch,
) -> None:
    """Runtime ingester status should serialize datetimes to ISO-8601 strings."""

    store = _Store(
        {
            "repository": {
                "runtime_family": "ingester",
                "ingester": "repository",
                "provider": "repository",
                "status": "idle",
                "last_attempt_at": datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
                "active_phase_started_at": datetime(
                    2026, 3, 22, 12, 0, 30, tzinfo=timezone.utc
                ),
                "active_last_progress_at": datetime(
                    2026, 3, 22, 12, 0, 45, tzinfo=timezone.utc
                ),
                "active_commit_started_at": datetime(
                    2026, 3, 22, 12, 0, 50, tzinfo=timezone.utc
                ),
                "updated_at": datetime(2026, 3, 22, 12, 1, tzinfo=timezone.utc),
            }
        }
    )
    monkeypatch.setattr(status_queries, "get_runtime_status_store", lambda: store)

    result = status_queries.get_ingester_status(object(), ingester="repository")

    assert result["last_attempt_at"] == "2026-03-22T12:00:00+00:00"
    assert result["active_phase_started_at"] == "2026-03-22T12:00:30+00:00"
    assert result["active_last_progress_at"] == "2026-03-22T12:00:45+00:00"
    assert result["active_commit_started_at"] == "2026-03-22T12:00:50+00:00"
    assert result["updated_at"] == "2026-03-22T12:01:00+00:00"


def test_request_ingester_scan_control_normalizes_datetime_fields(
    monkeypatch,
) -> None:
    """Manual ingester scan responses should serialize datetimes to ISO-8601 strings."""

    monkeypatch.setattr(
        status_queries,
        "request_ingester_scan",
        lambda **_kwargs: {
            "ingester": "repository",
            "scan_request_token": "scan-123",
            "scan_request_state": "pending",
            "scan_requested_at": datetime(2026, 3, 22, 12, 5, tzinfo=timezone.utc),
            "scan_requested_by": "api",
        },
    )

    result = status_queries.request_ingester_scan_control(
        object(),
        ingester="repository",
        requested_by="api",
    )

    assert result["scan_requested_at"] == "2026-03-22T12:05:00+00:00"

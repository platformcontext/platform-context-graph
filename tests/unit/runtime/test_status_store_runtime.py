from __future__ import annotations

from platform_context_graph.runtime import status_store_runtime


def test_runtime_status_persistence_active_requires_enabled_store(monkeypatch) -> None:
    """Runtime status persistence should require both config and a usable store."""

    class _FakeStore:
        def __init__(self, dsn: str) -> None:
            self.enabled = bool(dsn) and dsn == "postgresql://runtime-status"

    monkeypatch.setattr(
        status_store_runtime,
        "PostgresRuntimeStatusStore",
        _FakeStore,
    )
    monkeypatch.setenv("PCG_CONTENT_STORE_ENABLED", "true")
    monkeypatch.delenv("PCG_CONTENT_STORE_DSN", raising=False)
    monkeypatch.delenv("PCG_POSTGRES_DSN", raising=False)

    assert status_store_runtime.runtime_status_persistence_active() is False

    monkeypatch.setenv("PCG_POSTGRES_DSN", "postgresql://runtime-status")
    assert status_store_runtime.runtime_status_persistence_active() is True

    monkeypatch.setenv("PCG_CONTENT_STORE_ENABLED", "false")
    assert status_store_runtime.runtime_status_persistence_active() is False


def test_request_ingester_reindex_delegates_to_store(monkeypatch) -> None:
    """Remote admin reindex requests should delegate through the shared facade."""

    calls: list[dict[str, object]] = []

    class _FakeStore:
        enabled = True

        def request_reindex(
            self,
            *,
            ingester: str,
            requested_by: str,
            force: bool,
            scope: str,
        ) -> dict[str, object]:
            calls.append(
                {
                    "ingester": ingester,
                    "requested_by": requested_by,
                    "force": force,
                    "scope": scope,
                }
            )
            return {"reindex_request_token": "reindex-123"}

    monkeypatch.setattr(
        status_store_runtime,
        "get_runtime_status_store",
        lambda: _FakeStore(),
    )

    result = status_store_runtime.request_ingester_reindex(
        ingester="repository",
        requested_by="api",
        force=True,
        scope="workspace",
    )

    assert result == {"reindex_request_token": "reindex-123"}
    assert calls == [
        {
            "ingester": "repository",
            "requested_by": "api",
            "force": True,
            "scope": "workspace",
        }
    ]

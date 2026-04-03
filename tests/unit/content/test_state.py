from __future__ import annotations

from platform_context_graph.content import state


def test_content_store_dsn_resolution_active_requires_enabled_and_dsn(
    monkeypatch,
) -> None:
    """DSN resolution should only report active when config enables it and a DSN exists."""

    monkeypatch.setenv("PCG_CONTENT_STORE_ENABLED", "true")
    monkeypatch.delenv("PCG_CONTENT_STORE_DSN", raising=False)
    monkeypatch.delenv("PCG_POSTGRES_DSN", raising=False)

    assert state.content_store_dsn_resolution_active() is False

    monkeypatch.setenv("PCG_CONTENT_STORE_DSN", "postgresql://content-store")
    assert state.content_store_dsn_resolution_active() is True

    monkeypatch.setenv("PCG_CONTENT_STORE_ENABLED", "false")
    assert state.content_store_dsn_resolution_active() is False

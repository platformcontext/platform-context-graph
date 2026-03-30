"""Unit tests for batched PostgreSQL content reads."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from platform_context_graph.content.postgres_queries import get_file_contents_batch


def test_get_file_contents_batch_returns_mapping_for_requested_repo_files() -> None:
    """Batched content reads should return a repo/path keyed content mapping."""

    captured: dict[str, object] = {}

    class _FakeCursor:
        def execute(self, query: str, params: dict[str, object]) -> None:
            captured["query"] = query
            captured["params"] = params

        def fetchall(self):
            return [
                {
                    "repo_id": "repository:r_search",
                    "relative_path": "api-node-search.ts",
                    "content": "await api.start({ services: ['api-node-forex'] });",
                }
            ]

    @contextmanager
    def fake_cursor():
        yield _FakeCursor()

    provider = SimpleNamespace(_cursor=fake_cursor)

    result = get_file_contents_batch(
        provider,
        repo_files=[
            {
                "repo_id": "repository:r_search",
                "relative_path": "api-node-search.ts",
            },
            {
                "repo_id": "repository:r_catalog",
                "relative_path": "api-node-catalog.ts",
            },
        ],
    )

    assert "FROM content_files" in str(captured["query"])
    assert captured["params"] == {
        "repo_ids": ["repository:r_search", "repository:r_catalog"],
        "relative_paths": ["api-node-search.ts", "api-node-catalog.ts"],
    }
    assert result == {
        (
            "repository:r_search",
            "api-node-search.ts",
        ): "await api.start({ services: ['api-node-forex'] });"
    }


def test_get_file_contents_batch_skips_empty_requests() -> None:
    """Empty batch reads should not touch the database."""

    provider = SimpleNamespace(
        _cursor=lambda: (_ for _ in ()).throw(AssertionError("cursor not expected"))
    )

    assert get_file_contents_batch(provider, repo_files=[]) == {}

"""Unit tests for the PostgreSQL content provider."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from platform_context_graph.content.postgres import PostgresContentProvider


def test_delete_repository_content_removes_entities_and_files(monkeypatch) -> None:
    """Deleting repository content should purge entity and file rows for one repo."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.delete_repository_content("repository:r_test")

    queries = [call.args[0] for call in cursor.execute.call_args_list]
    params = [call.args[1] for call in cursor.execute.call_args_list]
    assert queries == [
        """
                DELETE FROM content_entities
                WHERE repo_id = %(repo_id)s
                """,
        """
                DELETE FROM content_files
                WHERE repo_id = %(repo_id)s
                """,
    ]
    assert params == [
        {"repo_id": "repository:r_test"},
        {"repo_id": "repository:r_test"},
    ]

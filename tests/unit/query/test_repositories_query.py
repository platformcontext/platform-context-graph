from __future__ import annotations

from platform_context_graph.query import repositories
from platform_context_graph.repository_identity import canonical_repository_id


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query: str, **_kwargs):
        assert "MATCH (r:Repository)" in query
        return _FakeResult(self._rows)


class _FakeDriver:
    def __init__(self, rows):
        self._rows = rows

    def session(self):
        return _FakeSession(self._rows)


class _FakeDatabase:
    def __init__(self, rows):
        self._rows = rows

    def get_driver(self):
        return _FakeDriver(self._rows)


def test_list_repositories_returns_canonical_repository_identifiers() -> None:
    rows = [
        {
            "name": "payments-api",
            "path": "/srv/repos/payments-api",
            "local_path": "/srv/repos/payments-api",
            "remote_url": "git@github.com:platformcontext/payments-api.git",
            "repo_slug": "platformcontext/payments-api",
            "has_remote": True,
            "is_dependency": False,
        },
        {
            "name": "shared-infra",
            "path": "/srv/repos/shared-infra",
            "local_path": "/srv/repos/shared-infra",
            "remote_url": "https://github.com/platformcontext/shared-infra.git",
            "repo_slug": "platformcontext/shared-infra",
            "has_remote": True,
            "is_dependency": True,
        },
    ]

    result = repositories.list_repositories(_FakeDatabase(rows))

    assert result == {
        "repositories": [
            {
                "id": canonical_repository_id(
                    remote_url="git@github.com:platformcontext/payments-api.git",
                    local_path="/srv/repos/payments-api",
                ),
                "name": "payments-api",
                "repo_slug": "platformcontext/payments-api",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "local_path": "/srv/repos/payments-api",
                "has_remote": True,
                "is_dependency": False,
            },
            {
                "id": canonical_repository_id(
                    remote_url="https://github.com/platformcontext/shared-infra.git",
                    local_path="/srv/repos/shared-infra",
                ),
                "name": "shared-infra",
                "repo_slug": "platformcontext/shared-infra",
                "remote_url": "https://github.com/platformcontext/shared-infra",
                "local_path": "/srv/repos/shared-infra",
                "has_remote": True,
                "is_dependency": True,
            },
        ]
    }

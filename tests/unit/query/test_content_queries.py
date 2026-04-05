from __future__ import annotations

from unittest.mock import MagicMock

from platform_context_graph.query import content as content_queries


class _MockResult:
    def __init__(self, records=None):
        self._records = records or []

    def data(self):
        return self._records


def _make_database(records: list[dict[str, object]]) -> MagicMock:
    database = MagicMock()
    driver = MagicMock()
    session = MagicMock()
    session.run.return_value = _MockResult(records=records)
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    database.get_driver.return_value = driver
    return database


def test_get_file_content_resolves_repo_names_to_canonical_ids(monkeypatch) -> None:
    """Content queries should accept plain repository names."""

    database = _make_database(
        [
            {
                "id": "repository:r_20871f7f",
                "name": "helm-charts",
                "path": "/data/repos/helm-charts",
                "local_path": "/data/repos/helm-charts",
                "remote_url": "https://github.com/platformcontext/helm-charts",
                "repo_slug": "platformcontext/helm-charts",
                "has_remote": True,
            }
        ]
    )
    captured: dict[str, object] = {}

    class _ContentService:
        def get_file_content(
            self, *, repo_id: str, relative_path: str
        ) -> dict[str, object]:
            captured["repo_id"] = repo_id
            captured["relative_path"] = relative_path
            return {
                "available": True,
                "repo_id": repo_id,
                "relative_path": relative_path,
                "source_backend": "postgres",
            }

    monkeypatch.setattr(
        content_queries,
        "get_content_service",
        lambda _database: _ContentService(),
    )

    result = content_queries.get_file_content(
        database,
        repo_id="helm-charts",
        relative_path="argocd/api-node-boats/base/xirsarole.yaml",
    )

    assert captured["repo_id"] == "repository:r_20871f7f"
    assert result["repo_id"] == "repository:r_20871f7f"


def test_get_file_lines_resolves_repo_names_to_canonical_ids(monkeypatch) -> None:
    """Line-range queries should share the same repo-name resolution path."""

    database = _make_database(
        [
            {
                "id": "repository:r_20871f7f",
                "name": "helm-charts",
                "path": "/data/repos/helm-charts",
                "local_path": "/data/repos/helm-charts",
                "remote_url": "https://github.com/platformcontext/helm-charts",
                "repo_slug": "platformcontext/helm-charts",
                "has_remote": True,
            }
        ]
    )
    captured: dict[str, object] = {}

    class _ContentService:
        def get_file_lines(
            self,
            *,
            repo_id: str,
            relative_path: str,
            start_line: int,
            end_line: int,
        ) -> dict[str, object]:
            captured["repo_id"] = repo_id
            captured["relative_path"] = relative_path
            captured["start_line"] = start_line
            captured["end_line"] = end_line
            return {
                "available": True,
                "repo_id": repo_id,
                "relative_path": relative_path,
                "start_line": start_line,
                "end_line": end_line,
            }

    monkeypatch.setattr(
        content_queries,
        "get_content_service",
        lambda _database: _ContentService(),
    )

    result = content_queries.get_file_lines(
        database,
        repo_id="helm-charts",
        relative_path="argocd/api-node-boats/base/xirsarole.yaml",
        start_line=1,
        end_line=20,
    )

    assert captured["repo_id"] == "repository:r_20871f7f"
    assert result["repo_id"] == "repository:r_20871f7f"


def test_search_file_content_resolves_repo_names_to_canonical_ids(
    monkeypatch,
) -> None:
    """File searches should normalize fuzzy repository filters before lookup."""

    database = _make_database(
        [
            {
                "id": "repository:r_20871f7f",
                "name": "helm-charts",
                "path": "/data/repos/helm-charts",
                "local_path": "/data/repos/helm-charts",
                "remote_url": "https://github.com/platformcontext/helm-charts",
                "repo_slug": "platformcontext/helm-charts",
                "has_remote": True,
            }
        ]
    )
    captured: dict[str, object] = {}

    class _ContentService:
        def search_file_content(
            self,
            *,
            pattern: str,
            repo_ids: list[str] | None = None,
            languages: list[str] | None = None,
            artifact_types: list[str] | None = None,
            template_dialects: list[str] | None = None,
            iac_relevant: bool | None = None,
        ) -> dict[str, object]:
            captured["pattern"] = pattern
            captured["repo_ids"] = repo_ids
            captured["languages"] = languages
            captured["artifact_types"] = artifact_types
            captured["template_dialects"] = template_dialects
            captured["iac_relevant"] = iac_relevant
            return {"pattern": pattern, "repo_ids": repo_ids or [], "matches": []}

    monkeypatch.setattr(
        content_queries,
        "get_content_service",
        lambda _database: _ContentService(),
    )

    result = content_queries.search_file_content(
        database,
        pattern="api-node-boats",
        repo_ids=["helm-charts"],
    )

    assert captured["repo_ids"] == ["repository:r_20871f7f"]
    assert result["repo_ids"] == ["repository:r_20871f7f"]

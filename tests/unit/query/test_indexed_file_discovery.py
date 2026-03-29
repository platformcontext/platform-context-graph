"""Tests for the Neo4j + Postgres indexed file discovery helpers."""

from __future__ import annotations

from typing import Any

import pytest

from platform_context_graph.query.repositories.indexed_file_discovery import (
    discover_repo_files,
    file_exists,
    read_file_content,
    read_yaml_file,
)

REPO_ID = "repository:r_test_repo"


# ---------------------------------------------------------------------------
# Stubs for the Neo4j driver / session
# ---------------------------------------------------------------------------


class _StubSession:
    """Minimal session stub that records Cypher queries and returns canned rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.last_query: str | None = None
        self.last_params: dict[str, Any] = {}

    def __enter__(self) -> "_StubSession":
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def run(self, query: str, **kwargs: Any) -> "_StubResult":
        """Capture the query and params, return canned data."""

        self.last_query = query
        self.last_params = kwargs
        return _StubResult(self._rows)


class _StubResult:
    """Minimal result stub exposing ``.data()``."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, Any]]:
        """Return canned rows."""

        return list(self._rows)


class _StubDriver:
    def __init__(self, session: _StubSession) -> None:
        self._session = session

    def session(self) -> _StubSession:
        """Return the pre-built stub session."""

        return self._session


class _StubDB:
    def __init__(self, session: _StubSession) -> None:
        self._driver = _StubDriver(session)

    def get_driver(self) -> _StubDriver:
        """Return the stub driver."""

        return self._driver


# ---------------------------------------------------------------------------
# discover_repo_files
# ---------------------------------------------------------------------------


class TestDiscoverRepoFiles:
    """Tests for discover_repo_files."""

    def test_returns_matching_files_with_prefix(self) -> None:
        """Files filtered by prefix are returned sorted."""

        session = _StubSession(
            [
                {"relative_path": "group_vars/all.yml"},
                {"relative_path": "group_vars/prod.yml"},
            ]
        )
        db = _StubDB(session)

        result = discover_repo_files(db, REPO_ID, prefix="group_vars/")

        assert result == ["group_vars/all.yml", "group_vars/prod.yml"]
        assert session.last_params["prefix"] == "group_vars/"
        assert session.last_params["suffix"] is None
        assert session.last_params["pattern"] is None

    def test_returns_matching_files_with_suffix(self) -> None:
        """Files filtered by suffix are returned."""

        session = _StubSession(
            [
                {"relative_path": "deploy/Jenkinsfile.groovy"},
                {"relative_path": "scripts/build.groovy"},
            ]
        )
        db = _StubDB(session)

        result = discover_repo_files(db, REPO_ID, suffix=".groovy")

        assert result == [
            "deploy/Jenkinsfile.groovy",
            "scripts/build.groovy",
        ]
        assert session.last_params["suffix"] == ".groovy"

    def test_returns_matching_files_with_pattern(self) -> None:
        """Files filtered by regex pattern are returned."""

        session = _StubSession(
            [{"relative_path": "roles/nginx/tasks/main.yml"}]
        )
        db = _StubDB(session)

        result = discover_repo_files(
            db, REPO_ID, pattern="roles/.*/tasks/main\\.y.*ml"
        )

        assert result == ["roles/nginx/tasks/main.yml"]
        assert session.last_params["pattern"] == "roles/.*/tasks/main\\.y.*ml"

    def test_returns_empty_list_when_no_matches(self) -> None:
        """An empty list is returned when no files match."""

        session = _StubSession([])
        db = _StubDB(session)

        result = discover_repo_files(db, REPO_ID, suffix=".tf")

        assert result == []

    def test_skips_rows_with_none_path(self) -> None:
        """Rows where relative_path is None are excluded."""

        session = _StubSession(
            [
                {"relative_path": "ok.yml"},
                {"relative_path": None},
            ]
        )
        db = _StubDB(session)

        result = discover_repo_files(db, REPO_ID)

        assert result == ["ok.yml"]

    def test_combined_prefix_and_suffix(self) -> None:
        """Both prefix and suffix can be supplied together."""

        session = _StubSession(
            [{"relative_path": ".github/workflows/ci.yml"}]
        )
        db = _StubDB(session)

        result = discover_repo_files(
            db, REPO_ID, prefix=".github/workflows/", suffix=".yml"
        )

        assert result == [".github/workflows/ci.yml"]
        assert session.last_params["prefix"] == ".github/workflows/"
        assert session.last_params["suffix"] == ".yml"


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExists:
    """Tests for file_exists."""

    def test_returns_true_when_file_exists(self) -> None:
        """True is returned when the file node is found."""

        session = _StubSession([{"exists": True}])
        db = _StubDB(session)

        assert file_exists(db, REPO_ID, "kustomization.yaml") is True

    def test_returns_false_when_file_missing(self) -> None:
        """False is returned when the file node is absent."""

        session = _StubSession([{"exists": False}])
        db = _StubDB(session)

        assert file_exists(db, REPO_ID, "nonexistent.txt") is False

    def test_returns_false_on_empty_result(self) -> None:
        """False is returned when the query returns no rows."""

        session = _StubSession([])
        db = _StubDB(session)

        assert file_exists(db, REPO_ID, "anything") is False


# ---------------------------------------------------------------------------
# read_file_content
# ---------------------------------------------------------------------------


class TestReadFileContent:
    """Tests for read_file_content."""

    def test_returns_content_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Content string is returned when the content store has it."""

        def _fake_get_file_content(_db: Any, *, repo_id: str, relative_path: str) -> dict:
            return {"available": True, "content": "hello world"}

        monkeypatch.setattr(
            "platform_context_graph.query.repositories.indexed_file_discovery.content_queries.get_file_content",
            _fake_get_file_content,
        )

        db = _StubDB(_StubSession([]))
        result = read_file_content(db, REPO_ID, "README.md")

        assert result == "hello world"

    def test_returns_none_when_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """None is returned when the content store has no content."""

        def _fake_get_file_content(_db: Any, *, repo_id: str, relative_path: str) -> dict:
            return {"available": False, "content": None}

        monkeypatch.setattr(
            "platform_context_graph.query.repositories.indexed_file_discovery.content_queries.get_file_content",
            _fake_get_file_content,
        )

        db = _StubDB(_StubSession([]))
        result = read_file_content(db, REPO_ID, "missing.txt")

        assert result is None

    def test_returns_none_when_content_not_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """None is returned when content is not a string."""

        def _fake_get_file_content(_db: Any, *, repo_id: str, relative_path: str) -> dict:
            return {"available": True, "content": 12345}

        monkeypatch.setattr(
            "platform_context_graph.query.repositories.indexed_file_discovery.content_queries.get_file_content",
            _fake_get_file_content,
        )

        db = _StubDB(_StubSession([]))
        result = read_file_content(db, REPO_ID, "file.bin")

        assert result is None


# ---------------------------------------------------------------------------
# read_yaml_file
# ---------------------------------------------------------------------------


class TestReadYamlFile:
    """Tests for read_yaml_file."""

    def test_returns_parsed_dict_for_valid_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dict is returned when the YAML is valid."""

        yaml_content = "name: my-app\nversion: 1.0\n"

        def _fake_get_file_content(_db: Any, *, repo_id: str, relative_path: str) -> dict:
            return {"available": True, "content": yaml_content}

        monkeypatch.setattr(
            "platform_context_graph.query.repositories.indexed_file_discovery.content_queries.get_file_content",
            _fake_get_file_content,
        )

        db = _StubDB(_StubSession([]))
        result = read_yaml_file(db, REPO_ID, "chart.yaml")

        assert result == {"name": "my-app", "version": 1.0}

    def test_returns_none_for_invalid_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """None is returned when the YAML is unparseable."""

        def _fake_get_file_content(_db: Any, *, repo_id: str, relative_path: str) -> dict:
            return {"available": True, "content": "{{invalid: yaml: ["}

        monkeypatch.setattr(
            "platform_context_graph.query.repositories.indexed_file_discovery.content_queries.get_file_content",
            _fake_get_file_content,
        )

        db = _StubDB(_StubSession([]))
        result = read_yaml_file(db, REPO_ID, "bad.yaml")

        assert result is None

    def test_returns_none_for_non_dict_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """None is returned when the YAML parses to a non-dict (e.g. a list)."""

        def _fake_get_file_content(_db: Any, *, repo_id: str, relative_path: str) -> dict:
            return {"available": True, "content": "- item1\n- item2\n"}

        monkeypatch.setattr(
            "platform_context_graph.query.repositories.indexed_file_discovery.content_queries.get_file_content",
            _fake_get_file_content,
        )

        db = _StubDB(_StubSession([]))
        result = read_yaml_file(db, REPO_ID, "list.yaml")

        assert result is None

    def test_returns_none_for_missing_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """None is returned when the file is not in the content store."""

        def _fake_get_file_content(_db: Any, *, repo_id: str, relative_path: str) -> dict:
            return {"available": False, "content": None}

        monkeypatch.setattr(
            "platform_context_graph.query.repositories.indexed_file_discovery.content_queries.get_file_content",
            _fake_get_file_content,
        )

        db = _StubDB(_StubSession([]))
        result = read_yaml_file(db, REPO_ID, "gone.yaml")

        assert result is None

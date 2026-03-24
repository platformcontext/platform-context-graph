"""Unit tests for the content service provider orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from platform_context_graph.content.service import ContentService


@dataclass
class _FakePostgresProvider:
    """Stub provider that records content-store calls."""

    file_result: dict | None = None
    entity_result: dict | None = None
    file_search_result: dict | None = None
    entity_search_result: dict | None = None
    file_calls: list[tuple[str, str]] | None = None
    entity_calls: list[str] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable call trackers."""

        if self.file_calls is None:
            self.file_calls = []
        if self.entity_calls is None:
            self.entity_calls = []

    @property
    def enabled(self) -> bool:
        """Return whether the fake provider should be treated as enabled."""

        return True

    def get_file_content(self, *, repo_id: str, relative_path: str) -> dict | None:
        """Return the stubbed file-content result."""

        self.file_calls.append((repo_id, relative_path))
        return self.file_result

    def get_entity_content(self, *, entity_id: str) -> dict | None:
        """Return the stubbed entity-content result."""

        self.entity_calls.append(entity_id)
        return self.entity_result

    def search_file_content(
        self,
        *,
        pattern: str,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
        artifact_types: list[str] | None = None,
        template_dialects: list[str] | None = None,
        iac_relevant: bool | None = None,
    ) -> dict:
        """Return the stubbed file-search result."""

        return self.file_search_result or {
            "pattern": pattern,
            "repo_ids": repo_ids or [],
            "languages": languages or [],
            "artifact_types": artifact_types or [],
            "template_dialects": template_dialects or [],
            "iac_relevant": iac_relevant,
            "matches": [],
        }

    def search_entity_content(
        self,
        *,
        pattern: str,
        entity_types: list[str] | None = None,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
        artifact_types: list[str] | None = None,
        template_dialects: list[str] | None = None,
        iac_relevant: bool | None = None,
    ) -> dict:
        """Return the stubbed entity-search result."""

        return self.entity_search_result or {
            "pattern": pattern,
            "entity_types": entity_types or [],
            "repo_ids": repo_ids or [],
            "languages": languages or [],
            "artifact_types": artifact_types or [],
            "template_dialects": template_dialects or [],
            "iac_relevant": iac_relevant,
            "matches": [],
        }


@dataclass
class _FakeWorkspaceProvider:
    """Stub workspace provider used to verify fallback behavior."""

    file_result: dict | None = None
    lines_result: dict | None = None
    entity_result: dict | None = None
    file_calls: list[tuple[str, str]] | None = None
    line_calls: list[tuple[str, str, int, int]] | None = None
    entity_calls: list[str] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable call trackers."""

        if self.file_calls is None:
            self.file_calls = []
        if self.line_calls is None:
            self.line_calls = []
        if self.entity_calls is None:
            self.entity_calls = []

    def get_file_content(self, *, repo_id: str, relative_path: str) -> dict:
        """Return the stubbed workspace file-content result."""

        self.file_calls.append((repo_id, relative_path))
        return self.file_result or {
            "available": True,
            "repo_id": repo_id,
            "relative_path": relative_path,
            "content": "workspace fallback",
            "line_count": 1,
            "language": "python",
            "source_backend": "workspace",
        }

    def get_file_lines(
        self,
        *,
        repo_id: str,
        relative_path: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        """Return the stubbed workspace line-range result."""

        self.line_calls.append((repo_id, relative_path, start_line, end_line))
        return self.lines_result or {
            "available": True,
            "repo_id": repo_id,
            "relative_path": relative_path,
            "start_line": start_line,
            "end_line": end_line,
            "lines": [
                {"line_number": start_line, "content": "workspace fallback"}
            ],
            "source_backend": "workspace",
        }

    def get_entity_content(self, *, entity_id: str) -> dict:
        """Return the stubbed workspace entity-content result."""

        self.entity_calls.append(entity_id)
        return self.entity_result or {
            "available": True,
            "entity_id": entity_id,
            "repo_id": "repository:r_ab12cd34",
            "relative_path": "src/service.py",
            "entity_type": "Function",
            "entity_name": "process_payment",
            "start_line": 10,
            "end_line": 18,
            "content": "def process_payment():\n    return True\n",
            "language": "python",
            "source_backend": "workspace",
        }


def test_get_file_content_prefers_postgres_and_skips_workspace_fallback() -> None:
    """Use the Postgres result when it already has cached file content."""

    postgres = _FakePostgresProvider(
        file_result={
            "available": True,
            "repo_id": "repository:r_ab12cd34",
            "relative_path": "src/payments.py",
            "content": "cached",
            "line_count": 1,
            "language": "python",
            "source_backend": "postgres",
        }
    )
    workspace = _FakeWorkspaceProvider()

    service = ContentService(
        postgres_provider=postgres,
        workspace_provider=workspace,
    )

    result = service.get_file_content(
        repo_id="repository:r_ab12cd34",
        relative_path="src/payments.py",
    )

    assert result["content"] == "cached"
    assert result["source_backend"] == "postgres"
    assert postgres.file_calls == [("repository:r_ab12cd34", "src/payments.py")]
    assert workspace.file_calls == []


def test_get_file_content_falls_back_to_workspace_when_postgres_misses() -> None:
    """Use workspace reads when the content store does not have the file row."""

    postgres = _FakePostgresProvider(file_result=None)
    workspace = _FakeWorkspaceProvider(
        file_result={
            "available": True,
            "repo_id": "repository:r_ab12cd34",
            "relative_path": "src/payments.py",
            "content": "workspace fallback",
            "line_count": 3,
            "language": "python",
            "source_backend": "workspace",
        }
    )

    service = ContentService(
        postgres_provider=postgres,
        workspace_provider=workspace,
    )

    result = service.get_file_content(
        repo_id="repository:r_ab12cd34",
        relative_path="src/payments.py",
    )

    assert result["content"] == "workspace fallback"
    assert result["source_backend"] == "workspace"
    assert postgres.file_calls == [("repository:r_ab12cd34", "src/payments.py")]
    assert workspace.file_calls == [("repository:r_ab12cd34", "src/payments.py")]


def test_get_entity_content_falls_back_to_workspace_when_postgres_misses() -> None:
    """Resolve entity source from the workspace when Postgres has no cached row."""

    postgres = _FakePostgresProvider(entity_result=None)
    workspace = _FakeWorkspaceProvider(
        entity_result={
            "available": True,
            "entity_id": "content-entity:e_ab12cd34ef56",
            "repo_id": "repository:r_ab12cd34",
            "relative_path": "src/service.py",
            "entity_type": "Function",
            "entity_name": "process_payment",
            "start_line": 10,
            "end_line": 18,
            "content": "def process_payment():\n    return True\n",
            "language": "python",
            "source_backend": "workspace",
        }
    )

    service = ContentService(
        postgres_provider=postgres,
        workspace_provider=workspace,
    )

    result = service.get_entity_content(entity_id="content-entity:e_ab12cd34ef56")

    assert result["entity_id"] == "content-entity:e_ab12cd34ef56"
    assert result["source_backend"] == "workspace"
    assert postgres.entity_calls == ["content-entity:e_ab12cd34ef56"]
    assert workspace.entity_calls == ["content-entity:e_ab12cd34ef56"]


def test_get_file_content_returns_not_indexed_when_workspace_fallback_is_disabled() -> None:
    """Return an explicit not-indexed response when Postgres misses and no workspace exists."""

    postgres = _FakePostgresProvider(file_result=None)

    service = ContentService(
        postgres_provider=postgres,
        workspace_provider=None,
    )

    result = service.get_file_content(
        repo_id="repository:r_ab12cd34",
        relative_path="src/payments.py",
    )

    assert result == {
        "available": False,
        "repo_id": "repository:r_ab12cd34",
        "relative_path": "src/payments.py",
        "content": None,
        "source_backend": "unavailable",
        "index_status": "not_indexed",
    }
    assert postgres.file_calls == [("repository:r_ab12cd34", "src/payments.py")]


def test_search_routes_to_postgres_content_store() -> None:
    """Run content search through the content store backend."""

    postgres = _FakePostgresProvider(
        file_search_result={
            "pattern": "payments",
            "matches": [
                {
                    "repo_id": "repository:r_ab12cd34",
                    "relative_path": "src/payments.py",
                    "language": "python",
                    "snippet": "payments",
                    "source_backend": "postgres",
                }
            ],
        },
        entity_search_result={
            "pattern": "process_payment",
            "matches": [
                {
                    "entity_id": "content-entity:e_ab12cd34ef56",
                    "repo_id": "repository:r_ab12cd34",
                    "relative_path": "src/payments.py",
                    "entity_type": "Function",
                    "entity_name": "process_payment",
                    "language": "python",
                    "snippet": "def process_payment",
                    "source_backend": "postgres",
                }
            ],
        },
    )

    service = ContentService(
        postgres_provider=postgres,
        workspace_provider=_FakeWorkspaceProvider(),
    )

    file_result = service.search_file_content(pattern="payments")
    entity_result = service.search_entity_content(pattern="process_payment")

    assert file_result["matches"][0]["source_backend"] == "postgres"
    assert entity_result["matches"][0]["entity_id"] == "content-entity:e_ab12cd34ef56"


def test_search_passes_metadata_filters_through_to_postgres() -> None:
    """Metadata filters should flow through the content service unchanged."""

    postgres = _FakePostgresProvider()
    service = ContentService(
        postgres_provider=postgres,
        workspace_provider=_FakeWorkspaceProvider(),
    )

    file_result = service.search_file_content(
        pattern="python",
        artifact_types=["dockerfile"],
        template_dialects=["jinja"],
        iac_relevant=True,
    )
    entity_result = service.search_entity_content(
        pattern="service",
        artifact_types=["terraform_hcl"],
        template_dialects=["terraform_template"],
        iac_relevant=True,
    )

    assert file_result["artifact_types"] == ["dockerfile"]
    assert file_result["template_dialects"] == ["jinja"]
    assert file_result["iac_relevant"] is True
    assert entity_result["artifact_types"] == ["terraform_hcl"]
    assert entity_result["template_dialects"] == ["terraform_template"]
    assert entity_result["iac_relevant"] is True

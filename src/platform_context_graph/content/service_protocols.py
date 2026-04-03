"""Structural protocols used by the content service."""

from __future__ import annotations

from typing import Any, Protocol

__all__ = [
    "PostgresProviderProtocol",
    "WorkspaceProviderProtocol",
]


class PostgresProviderProtocol(Protocol):
    """Structural protocol for the PostgreSQL-backed content provider."""

    @property
    def enabled(self) -> bool:
        """Return whether the provider is enabled."""

    def delete_repository_content(self, repo_id: str) -> None:
        """Delete cached content for one repository."""

    def get_file_content(
        self, *, repo_id: str, relative_path: str
    ) -> dict[str, Any] | None:
        """Return cached file content when available."""

    def get_entity_content(self, *, entity_id: str) -> dict[str, Any] | None:
        """Return cached entity content when available."""

    def search_file_content(
        self,
        *,
        pattern: str,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
        artifact_types: list[str] | None = None,
        template_dialects: list[str] | None = None,
        iac_relevant: bool | None = None,
    ) -> dict[str, Any]:
        """Search cached file content."""

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
    ) -> dict[str, Any]:
        """Search cached entity snippets."""


class WorkspaceProviderProtocol(Protocol):
    """Structural protocol for workspace-backed content retrieval."""

    def get_file_content(self, *, repo_id: str, relative_path: str) -> dict[str, Any]:
        """Read one file from the workspace."""

    def get_file_lines(
        self,
        *,
        repo_id: str,
        relative_path: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        """Read one file line range from the workspace."""

    def get_entity_content(self, *, entity_id: str) -> dict[str, Any]:
        """Read one entity snippet from the workspace or graph cache."""

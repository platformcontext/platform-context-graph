"""Provider orchestration for content retrieval and search."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from ..observability import get_observability

__all__ = [
    "ContentService",
]


class _PostgresProvider(Protocol):
    """Structural protocol for the PostgreSQL-backed content provider."""

    @property
    def enabled(self) -> bool:
        """Return whether the provider is enabled."""

    def delete_repository_content(self, repo_id: str) -> None:
        """Delete cached content for one repository."""

    def get_file_content(self, *, repo_id: str, relative_path: str) -> dict[str, Any] | None:
        """Return cached file content when available."""

    def get_entity_content(self, *, entity_id: str) -> dict[str, Any] | None:
        """Return cached entity content when available."""

    def search_file_content(
        self,
        *,
        pattern: str,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search cached file content."""

    def search_entity_content(
        self,
        *,
        pattern: str,
        entity_types: list[str] | None = None,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search cached entity snippets."""


class _WorkspaceProvider(Protocol):
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


@dataclass(slots=True)
class ContentService:
    """Orchestrate content retrieval across Postgres and workspace providers."""

    postgres_provider: _PostgresProvider | None
    workspace_provider: _WorkspaceProvider

    def get_file_content(self, *, repo_id: str, relative_path: str) -> dict[str, Any]:
        """Return file content using Postgres first and the workspace second.

        Args:
            repo_id: Canonical repository identifier.
            relative_path: Repo-relative file path.

        Returns:
            Content response mapping.
        """

        postgres_result = self._from_postgres_file(
            repo_id=repo_id,
            relative_path=relative_path,
        )
        if postgres_result is not None:
            return postgres_result
        return self._workspace_result(
            "file",
            self.workspace_provider.get_file_content,
            repo_id=repo_id,
            relative_path=relative_path,
        )

    def get_file_lines(
        self,
        *,
        repo_id: str,
        relative_path: str,
        start_line: int,
        end_line: int,
    ) -> dict[str, Any]:
        """Return one line range from the workspace.

        Args:
            repo_id: Canonical repository identifier.
            relative_path: Repo-relative file path.
            start_line: First line to include.
            end_line: Last line to include.

        Returns:
            Line-range response mapping.
        """

        return self._workspace_result(
            "lines",
            self.workspace_provider.get_file_lines,
            repo_id=repo_id,
            relative_path=relative_path,
            start_line=start_line,
            end_line=end_line,
        )

    def get_entity_content(self, *, entity_id: str) -> dict[str, Any]:
        """Return source for one content-bearing entity.

        Args:
            entity_id: Canonical content entity identifier.

        Returns:
            Entity content response mapping.
        """

        postgres_result = self._from_postgres_entity(entity_id=entity_id)
        if postgres_result is not None:
            return postgres_result
        return self._workspace_result(
            "entity",
            self.workspace_provider.get_entity_content,
            entity_id=entity_id,
        )

    def search_file_content(
        self,
        *,
        pattern: str,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search file content through the PostgreSQL content store.

        Args:
            pattern: Search pattern.
            repo_ids: Optional repository filters.
            languages: Optional language filters.

        Returns:
            Search response mapping.
        """

        provider = self.postgres_provider
        if provider is None or not provider.enabled:
            return {
                "error": "Content search requires the PostgreSQL content store.",
                "pattern": pattern,
                "matches": [],
            }
        return self._postgres_result(
            operation="search_file_content",
            backend="postgres",
            call=provider.search_file_content,
            pattern=pattern,
            repo_ids=repo_ids,
            languages=languages,
        )

    def search_entity_content(
        self,
        *,
        pattern: str,
        entity_types: list[str] | None = None,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search entity snippets through the PostgreSQL content store.

        Args:
            pattern: Search pattern.
            entity_types: Optional entity-type filters.
            repo_ids: Optional repository filters.
            languages: Optional language filters.

        Returns:
            Search response mapping.
        """

        provider = self.postgres_provider
        if provider is None or not provider.enabled:
            return {
                "error": "Entity content search requires the PostgreSQL content store.",
                "pattern": pattern,
                "matches": [],
            }
        return self._postgres_result(
            operation="search_entity_content",
            backend="postgres",
            call=provider.search_entity_content,
            pattern=pattern,
            entity_types=entity_types,
            repo_ids=repo_ids,
            languages=languages,
        )

    def _from_postgres_file(
        self, *, repo_id: str, relative_path: str
    ) -> dict[str, Any] | None:
        """Attempt to retrieve file content from PostgreSQL.

        Args:
            repo_id: Canonical repository identifier.
            relative_path: Repo-relative file path.

        Returns:
            PostgreSQL-backed response mapping or ``None`` when not found.
        """

        provider = self.postgres_provider
        if provider is None or not provider.enabled:
            return None

        return self._postgres_result(
            operation="get_file_content",
            backend="postgres",
            call=provider.get_file_content,
            repo_id=repo_id,
            relative_path=relative_path,
        )

    def _from_postgres_entity(self, *, entity_id: str) -> dict[str, Any] | None:
        """Attempt to retrieve entity content from PostgreSQL.

        Args:
            entity_id: Canonical content entity identifier.

        Returns:
            PostgreSQL-backed response mapping or ``None`` when not found.
        """

        provider = self.postgres_provider
        if provider is None or not provider.enabled:
            return None

        return self._postgres_result(
            operation="get_entity_content",
            backend="postgres",
            call=provider.get_entity_content,
            entity_id=entity_id,
        )

    def _postgres_result(
        self,
        operation: str,
        backend: str,
        call: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Execute one PostgreSQL-backed content operation with metrics.

        Args:
            operation: Logical content operation name.
            backend: Backend name for observability attributes.
            call: Bound provider method.
            **kwargs: Arguments for the provider method.

        Returns:
            Provider response mapping, or ``None`` when the provider misses.
        """

        runtime = get_observability()
        started = time.perf_counter()
        success = False
        hit = False
        try:
            result = call(**kwargs)
            success = True
            hit = bool(result)
            return result
        finally:
            self._record_provider_metrics(
                operation=operation,
                backend=backend,
                success=success,
                hit=hit,
                duration_seconds=time.perf_counter() - started,
            )

    def _workspace_result(
        self,
        operation: str,
        call: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute one workspace-backed content operation with metrics.

        Args:
            operation: Logical content operation name.
            call: Bound workspace-provider method.
            **kwargs: Arguments for the provider method.

        Returns:
            Provider response mapping.
        """

        runtime = get_observability()
        started = time.perf_counter()
        success = False
        hit = False
        try:
            result = call(**kwargs)
            success = True
            hit = bool(result.get("available"))
            return result
        finally:
            self._record_provider_metrics(
                operation=operation,
                backend="workspace",
                success=success,
                hit=hit,
                duration_seconds=time.perf_counter() - started,
            )
            if hasattr(runtime, "record_content_workspace_fallback") and operation in {
                "file",
                "entity",
                "lines",
            }:
                runtime.record_content_workspace_fallback(operation=operation)

    def _record_provider_metrics(
        self,
        *,
        operation: str,
        backend: str,
        success: bool,
        hit: bool,
        duration_seconds: float,
    ) -> None:
        """Record content-provider metrics when observability is enabled.

        Args:
            operation: Logical content operation name.
            backend: Backend name.
            success: Whether the provider call succeeded.
            hit: Whether the provider returned a row/result.
            duration_seconds: Provider call duration.
        """

        runtime = get_observability()
        if hasattr(runtime, "record_content_provider_result"):
            runtime.record_content_provider_result(
                operation=operation,
                backend=backend,
                success=success,
                hit=hit,
                duration_seconds=duration_seconds,
            )

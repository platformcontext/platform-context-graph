"""Facade module exposing the public ``GraphBuilder`` interface."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..cli.helpers.go_index_runtime import run_go_bootstrap_index
from ..core.database import DatabaseManager
from ..core.jobs import JobManager
from ..relationships import (
    resolve_repository_relationships_for_committed_repositories as _resolve_repository_relationships_for_committed_repositories,
)
from ..utils.debug_log import info_logger, warning_logger
from ..utils.debug_log import debug_logger
from ..graph.persistence import (
    delete_repository_from_graph as _delete_repository_from_graph,
    reset_repository_subtree_in_graph as _reset_repository_subtree_in_graph,
)
from ..graph.schema import create_schema as _create_schema


class GraphBuilder:
    """Build and maintain the repository code graph."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        job_manager: JobManager,
        loop: asyncio.AbstractEventLoop,
    ):
        """Initialize the graph builder facade and parser registry.

        Args:
            db_manager: Database manager backing graph persistence.
            job_manager: Background job tracker used during indexing.
            loop: Event loop used for async indexing workflows.
        """
        self.db_manager = db_manager
        self.job_manager = job_manager
        self.loop = loop
        self.driver = self.db_manager.get_driver()
        self.create_schema()

    def create_schema(self) -> None:
        """Create graph schema constraints and indexes."""
        _create_schema(
            self, info_logger_fn=info_logger, warning_logger_fn=warning_logger
        )

    def _resolve_repository_relationships(
        self,
        committed_repo_paths: list[Path],
        *,
        run_id: str | None = None,
    ) -> dict[str, int]:
        """Resolve repository dependencies from graph evidence into Postgres and Neo4j."""

        return _resolve_repository_relationships_for_committed_repositories(
            builder=self,
            committed_repo_paths=committed_repo_paths,
            run_id=run_id,
            info_logger_fn=info_logger,
        )

    def delete_repository_from_graph(self, repo_identifier: str) -> bool:
        """Delete one repository subtree from the graph.

        Args:
            repo_identifier: Canonical repository id or repository path.

        Returns:
            ``True`` if the repository existed and was deleted.
        """
        return _delete_repository_from_graph(
            self,
            repo_identifier,
            info_logger_fn=info_logger,
            debug_logger_fn=debug_logger,
            warning_logger_fn=warning_logger,
        )

    def reset_repository_subtree_in_graph(self, repo_identifier: str) -> bool:
        """Delete repo-owned descendants while preserving the Repository node.

        Args:
            repo_identifier: Canonical repository id or repository path.

        Returns:
            ``True`` if the repository existed and its subtree was reset.
        """

        return _reset_repository_subtree_in_graph(
            self,
            repo_identifier,
            info_logger_fn=info_logger,
            debug_logger_fn=debug_logger,
            warning_logger_fn=warning_logger,
        )

    async def build_graph_from_path_async(
        self,
        path: Path,
        is_dependency: bool = False,
        job_id: str | None = None,
        *,
        force: bool = False,
        selected_repositories: list[Path] | tuple[Path, ...] | None = None,
        family: str = "index",
        source: str | None = None,
        component: str = "cli",
    ) -> None:
        """Build the graph from a file or directory path.

        Args:
            path: File or directory to index.
            is_dependency: Whether the path is being indexed as a dependency.
            job_id: Optional background job identifier.
            force: Whether to invalidate an existing checkpoint for the same run.
            selected_repositories: Optional repository subset for batch indexing.
            family: Run family label used in checkpointing and telemetry.
            source: Source label used in checkpointing and telemetry.
            component: Observability component label for the indexing run.
        """
        if path.is_dir() or path.is_file() or selected_repositories:
            to_thread = getattr(asyncio, "to_thread", None)
            if callable(to_thread):
                await to_thread(
                    run_go_bootstrap_index,
                    path,
                    selected_repositories=selected_repositories,
                    force=force,
                    is_dependency=is_dependency,
                )
            else:
                run_go_bootstrap_index(
                    path,
                    selected_repositories=selected_repositories,
                    force=force,
                    is_dependency=is_dependency,
                )
            return


__all__ = ["GraphBuilder"]

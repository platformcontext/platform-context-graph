"""Facade module exposing the public ``GraphBuilder`` interface."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pathspec

from ..cli.config_manager import get_config_value
from ..core.database import DatabaseManager
from ..core.jobs import JobManager, JobStatus
from ..indexing import execute_index_run, raise_for_failed_index_run
from ..observability import get_observability
from ..relationships import (
    resolve_repository_relationships_for_committed_repositories as _resolve_repository_relationships_for_committed_repositories,
)
from ..repository_identity import git_remote_for_path, repository_metadata
from ..utils.debug_log import debug_log, error_logger, info_logger, warning_logger
from ..utils.debug_log import debug_logger
from .graph_builder_indexing import (
    build_graph_from_path_async as _build_graph_from_path_async,
    collect_supported_files as _collect_supported_files,
    estimate_processing_time as _estimate_processing_time,
    get_ignored_dir_names as _get_ignored_dir_names,
)
from .graph_builder_mutations import (
    delete_file_from_graph as _delete_file_from_graph,
    delete_repository_from_graph as _delete_repository_from_graph,
    update_file_in_graph as _update_file_in_graph,
)
from .graph_builder_parsers import (
    TreeSitterParser,
    build_parser_registry,
    parse_file as _parse_file,
    pre_scan_for_imports as _pre_scan_for_imports,
)
from .graph_builder_persistence import (
    add_file_to_graph as _add_file_to_graph,
    add_repository_to_graph as _add_repository_to_graph,
    commit_file_batch_to_graph as _commit_file_batch_to_graph,
)
from .graph_builder_relationships import (
    create_all_function_calls as _create_all_function_calls,
    create_all_infra_links as _create_all_infra_links,
    create_all_inheritance_links as _create_all_inheritance_links,
    create_csharp_inheritance_and_interfaces as _create_csharp_inheritance_and_interfaces,
    create_function_calls as _create_function_calls,
    create_inheritance_links as _create_inheritance_links,
    name_from_symbol as _name_from_symbol,
    safe_run_create as _safe_run_create,
)
from .graph_builder_schema import create_schema as _create_schema
from .graph_builder_scip import build_graph_from_scip as _build_graph_from_scip
from .graph_builder_workloads import materialize_workloads as _materialize_workloads


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
        self.parsers = build_parser_registry(get_config_value)
        self.create_schema()

    def create_schema(self) -> None:
        """Create graph schema constraints and indexes."""
        _create_schema(
            self, info_logger_fn=info_logger, warning_logger_fn=warning_logger
        )

    def _pre_scan_for_imports(self, files: list[Path]) -> dict[str, Any]:
        """Collect import resolution hints before indexing files."""
        return _pre_scan_for_imports(self, files)

    def add_repository_to_graph(
        self, repo_path: Path, is_dependency: bool = False
    ) -> None:
        """Add or update a repository node in the graph.

        Args:
            repo_path: Repository root path.
            is_dependency: Whether the repository is a dependency index target.
        """
        _add_repository_to_graph(
            self,
            repo_path,
            is_dependency,
            git_remote_for_path_fn=git_remote_for_path,
            repository_metadata_fn=repository_metadata,
        )

    def add_file_to_graph(
        self, file_data: dict[str, Any], repo_name: str, imports_map: dict[str, Any]
    ) -> None:
        """Persist one parsed file and its contained graph nodes.

        Args:
            file_data: Parsed file payload.
            repo_name: Repository name retained for signature compatibility.
            imports_map: Import resolution map retained for signature compatibility.
        """
        _add_file_to_graph(
            self,
            file_data,
            repo_name,
            imports_map,
            debug_log_fn=debug_log,
            info_logger_fn=info_logger,
            warning_logger_fn=warning_logger,
        )

    def commit_file_batch_to_graph(
        self,
        file_data_list: list[dict[str, Any]],
        repo_path: Path,
        *,
        progress_callback: Any | None = None,
    ) -> Any:
        """Persist a batch of parsed files in a single Neo4j transaction.

        Args:
            file_data_list: List of parsed file payloads.
            repo_path: Repository root path for the batch.
            progress_callback: Optional heartbeat callback invoked per file.
        """
        return _commit_file_batch_to_graph(
            self,
            file_data_list,
            repo_path,
            progress_callback=progress_callback,
            debug_log_fn=debug_log,
            info_logger_fn=info_logger,
            warning_logger_fn=warning_logger,
        )

    def _safe_run_create(
        self, session: Any, query: str, params: dict[str, Any]
    ) -> bool:
        """Run a relationship creation query and report whether it created rows."""
        return _safe_run_create(session, query, params)

    def _create_function_calls(
        self, session: Any, file_data: dict[str, Any], imports_map: dict[str, Any]
    ) -> None:
        """Create ``CALLS`` relationships for one parsed file."""
        _create_function_calls(
            self,
            session,
            file_data,
            imports_map,
            debug_log_fn=debug_log,
            get_config_value_fn=get_config_value,
            warning_logger_fn=warning_logger,
        )

    def _create_all_function_calls(
        self,
        all_file_data: Any,
        imports_map: dict[str, Any],
        *,
        progress_callback: Any | None = None,
    ) -> dict[str, float | int]:
        """Create ``CALLS`` relationships after all files are indexed."""
        return _create_all_function_calls(
            self,
            all_file_data,
            imports_map,
            debug_log_fn=debug_log,
            get_config_value_fn=get_config_value,
            warning_logger_fn=warning_logger,
            progress_callback=progress_callback,
        )

    def _create_all_infra_links(self, all_file_data: Any) -> None:
        """Create infrastructure relationships after indexing completes."""
        _create_all_infra_links(self, all_file_data, info_logger_fn=info_logger)

    def _materialize_workloads(
        self,
        committed_repo_paths: list[Path] | None = None,
        *,
        progress_callback: Any | None = None,
    ) -> dict[str, int]:
        """Materialize canonical workloads after cross-repo links are in place."""
        return _materialize_workloads(
            self,
            info_logger_fn=info_logger,
            committed_repo_paths=committed_repo_paths,
            progress_callback=progress_callback,
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

    def _create_inheritance_links(
        self, session: Any, file_data: dict[str, Any], imports_map: dict[str, Any]
    ) -> None:
        """Create inheritance edges for one parsed file."""
        _create_inheritance_links(session, file_data, imports_map)

    def _create_csharp_inheritance_and_interfaces(
        self, session: Any, file_data: dict[str, Any], imports_map: dict[str, Any]
    ) -> None:
        """Create inheritance and implementation edges for one C# file."""
        _create_csharp_inheritance_and_interfaces(session, file_data, imports_map)

    def _create_all_inheritance_links(
        self, all_file_data: Any, imports_map: dict[str, Any]
    ) -> None:
        """Create inheritance-style relationships after all files are indexed."""
        _create_all_inheritance_links(self, all_file_data, imports_map)

    def delete_file_from_graph(self, path: str) -> None:
        """Delete one file subtree from the graph.

        Args:
            path: File path to remove.
        """
        _delete_file_from_graph(self, path, info_logger_fn=info_logger)

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

    def update_file_in_graph(
        self, path: Path, repo_path: Path, imports_map: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Refresh graph state for one file.

        Args:
            path: File path to refresh.
            repo_path: Repository root containing the file.
            imports_map: Import resolution map used for follow-up relationships.

        Returns:
            Parsed file data, a deletion marker, or ``None`` if parsing failed.
        """
        return _update_file_in_graph(
            self,
            path,
            repo_path,
            imports_map,
            error_logger_fn=error_logger,
        )

    def parse_file(
        self, repo_path: Path, path: Path, is_dependency: bool = False
    ) -> dict[str, Any]:
        """Parse one file with the registered language parser."""
        return _parse_file(
            self,
            repo_path,
            path,
            is_dependency,
            get_config_value_fn=get_config_value,
            debug_log_fn=debug_log,
            error_logger_fn=error_logger,
            warning_logger_fn=warning_logger,
        )

    def estimate_processing_time(self, path: Path) -> tuple[int, float] | None:
        """Estimate indexing duration for a file or directory."""
        return _estimate_processing_time(self, path, error_logger_fn=error_logger)

    def _get_ignored_dir_names(self) -> set[str]:
        """Return configured hidden directory names that should be skipped."""
        return _get_ignored_dir_names(get_config_value_fn=get_config_value)

    def _collect_supported_files(self, path: Path) -> list[Path]:
        """Collect files whose extensions are supported by the parser registry."""
        return _collect_supported_files(
            self,
            path,
            get_config_value_fn=get_config_value,
            get_observability_fn=get_observability,
            os_module=os,
        )

    async def _build_graph_from_scip(
        self, path: Path, is_dependency: bool, job_id: str | None, lang: str
    ) -> None:
        """Index a path via SCIP output when the feature is enabled."""
        await _build_graph_from_scip(
            self,
            path,
            is_dependency,
            job_id,
            lang,
            asyncio_module=asyncio,
            datetime_cls=datetime,
            debug_log_fn=debug_log,
            error_logger_fn=error_logger,
            warning_logger_fn=warning_logger,
            job_status_enum=JobStatus,
        )

    def _name_from_symbol(self, symbol: str) -> str:
        """Extract a readable function name from a SCIP symbol identifier."""
        return _name_from_symbol(symbol)

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
        if path.is_dir() or selected_repositories:
            result = await execute_index_run(
                self,
                path,
                is_dependency=is_dependency,
                job_id=job_id,
                selected_repositories=selected_repositories,
                family=family,
                source=source or os.getenv("PCG_REPO_SOURCE_MODE", "manual"),
                force=force,
                component=component,
                asyncio_module=asyncio,
                datetime_cls=datetime,
                info_logger_fn=info_logger,
                warning_logger_fn=warning_logger,
                error_logger_fn=error_logger,
                job_status_enum=JobStatus,
                pathspec_module=pathspec,
            )
            raise_for_failed_index_run(result)
            return

        # Delegate the single-file .pcgignore-aware indexing flow to the helper module.
        await _build_graph_from_path_async(
            self,
            path,
            is_dependency,
            job_id,
            asyncio_module=asyncio,
            datetime_cls=datetime,
            debug_log_fn=debug_log,
            error_logger_fn=error_logger,
            get_config_value_fn=get_config_value,
            info_logger_fn=info_logger,
            pathspec_module=pathspec,
            warning_logger_fn=warning_logger,
            job_status_enum=JobStatus,
        )


__all__ = ["GraphBuilder", "TreeSitterParser"]

"""Child-process entry points for ProcessPoolExecutor-based commit workers.

This module provides top-level functions for executing file batch commits
in isolated child processes, fixing GIL starvation when multiple commit
workers run simultaneously.

The Neo4j driver and Postgres content provider are cached as process-level
globals so that each child process reuses its connection pool across batches.
Connections are cleaned up when the process pool shuts down (OS terminates
the child processes).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import neo4j

from ...content.postgres import PostgresContentProvider
from ...core.database import Neo4jDriverWrapper

# Import the module to access its globals
from ... import content
from ...tools.graph_builder_persistence import (
    BatchCommitResult,
    commit_file_batch_to_graph,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "commit_batch_in_process",
    "get_commit_worker_connection_params",
]

# Process-level cached Neo4j driver and wrapper. Created on first batch,
# reused across all subsequent batches in the same child process.
# ProcessPoolExecutor dispatches one task per worker at a time, so
# no concurrent access within a single child process.
_cached_driver: neo4j.Driver | None = None
_cached_driver_wrapper: Neo4jDriverWrapper | None = None
_cached_driver_key: tuple[str, str, str, str | None] | None = None


def _get_or_create_driver(
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str | None,
) -> Neo4jDriverWrapper:
    """Return a cached Neo4j driver wrapper, creating it on first call.

    The driver is keyed by (uri, username, password, database). If the
    connection params change (shouldn't happen in practice), a new driver
    is created and the old one is closed.

    Args:
        neo4j_uri: Neo4j connection URI.
        neo4j_username: Neo4j authentication username.
        neo4j_password: Neo4j authentication password.
        neo4j_database: Optional Neo4j database name.

    Returns:
        A Neo4jDriverWrapper with a cached underlying driver.
    """
    global _cached_driver, _cached_driver_wrapper, _cached_driver_key

    key = (neo4j_uri, neo4j_username, neo4j_password, neo4j_database)
    if _cached_driver is not None and _cached_driver_key == key:
        return _cached_driver_wrapper  # type: ignore[return-value]

    # Close stale driver if params changed
    if _cached_driver is not None:
        try:
            _cached_driver.close()
        except Exception:
            pass

    _cached_driver = neo4j.GraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_username, neo4j_password),
    )
    _cached_driver_wrapper = Neo4jDriverWrapper(_cached_driver, database=neo4j_database)
    _cached_driver_key = key
    return _cached_driver_wrapper


def _init_postgres_content_provider(dsn: str) -> None:
    """Initialize the global Postgres content provider in a child process.

    Args:
        dsn: PostgreSQL connection string.
    """
    state_module = content.state
    with state_module._LOCK:
        if state_module._POSTGRES_PROVIDER is None:
            state_module._POSTGRES_PROVIDER = PostgresContentProvider(dsn)


class _WorkerBuilder:
    """Minimal builder facade for child process commit workers.

    Provides just enough interface to satisfy commit_file_batch_to_graph.
    Only ``self.driver`` is accessed by the persistence layer.
    """

    def __init__(self, driver_wrapper: Neo4jDriverWrapper):
        """Initialize with a Neo4j driver wrapper.

        Args:
            driver_wrapper: Wrapped Neo4j driver for graph writes.
        """
        self.driver = driver_wrapper


def commit_batch_in_process(
    *,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    neo4j_database: str | None,
    postgres_dsn: str | None,
    file_data_list: list[dict],
    repo_path: str,
    adaptive_flush_threshold: int | None = None,
    adaptive_entity_batch_size: int | None = None,
    adaptive_tx_file_limit: int | None = None,
    adaptive_content_batch_size: int | None = None,
) -> BatchCommitResult:
    """Execute one file batch commit in an isolated child process.

    Uses a cached Neo4j driver and Postgres content provider so that
    repeated batch invocations in the same child process reuse TCP
    connections rather than paying setup overhead per batch.

    This function is designed to be used with ProcessPoolExecutor, so it
    and its arguments must be picklable.

    Args:
        neo4j_uri: Neo4j connection URI (e.g., "bolt://localhost:7687").
        neo4j_username: Neo4j authentication username.
        neo4j_password: Neo4j authentication password.
        neo4j_database: Optional Neo4j database name.
        postgres_dsn: Optional PostgreSQL DSN for content store dual-writes.
        file_data_list: List of parsed file data dicts to commit.
        repo_path: Absolute path to the repository root.
        adaptive_flush_threshold: Optional entity flush threshold override.
        adaptive_entity_batch_size: Optional entity batch size override.
        adaptive_tx_file_limit: Optional transaction file limit override.
        adaptive_content_batch_size: Optional content batch size override.

    Returns:
        BatchCommitResult with committed/failed files and timing metrics.

    Raises:
        Exception: Any exception from the commit operation is propagated.
    """
    driver_wrapper = _get_or_create_driver(
        neo4j_uri, neo4j_username, neo4j_password, neo4j_database
    )

    if postgres_dsn:
        _init_postgres_content_provider(postgres_dsn)

    builder = _WorkerBuilder(driver_wrapper)

    return commit_file_batch_to_graph(
        builder,
        file_data_list=file_data_list,
        repo_path=Path(repo_path),
        progress_callback=None,
        debug_log_fn=_logger.debug,
        info_logger_fn=_logger.info,
        warning_logger_fn=_logger.warning,
        adaptive_flush_threshold=adaptive_flush_threshold,
        adaptive_entity_batch_size=adaptive_entity_batch_size,
        adaptive_tx_file_limit=adaptive_tx_file_limit,
        adaptive_content_batch_size=adaptive_content_batch_size,
    )


def get_commit_worker_connection_params() -> dict[str, str | None]:
    """Return serializable connection params for child process workers.

    Reads Neo4j and PostgreSQL connection information from environment
    variables. Used to prepare arguments for commit_batch_in_process.

    Returns:
        Dictionary with keys: neo4j_uri, neo4j_username, neo4j_password,
        neo4j_database, postgres_dsn. Values are strings or None.

    Raises:
        ValueError: If NEO4J_URI is not set (required for graph writes).
    """
    neo4j_uri = os.getenv("NEO4J_URI")
    if not neo4j_uri:
        raise ValueError(
            "NEO4J_URI environment variable is required for "
            "ProcessPoolExecutor commit workers"
        )

    neo4j_username = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    neo4j_database = os.getenv("NEO4J_DATABASE")

    postgres_dsn = None
    for key in ("PCG_CONTENT_STORE_DSN", "PCG_POSTGRES_DSN"):
        value = os.getenv(key)
        if value and value.strip():
            postgres_dsn = value.strip()
            break

    return {
        "neo4j_uri": neo4j_uri,
        "neo4j_username": neo4j_username,
        "neo4j_password": neo4j_password,
        "neo4j_database": neo4j_database,
        "postgres_dsn": postgres_dsn,
    }

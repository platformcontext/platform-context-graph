"""Neo4j + Postgres file discovery helpers for API-mode enrichment.

Replaces filesystem glob/rglob/iterdir/read_text with indexed lookups
against Neo4j File nodes and Postgres content store.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

from ...query import content as content_queries
from .common import get_db_manager

logger = logging.getLogger(__name__)


def discover_repo_files(
    database: Any,
    repo_id: str,
    *,
    prefix: str | None = None,
    suffix: str | None = None,
    pattern: str | None = None,
) -> list[str]:
    """Return relative paths of files in a repo matching the given criteria.

    Uses Neo4j File nodes linked by REPO_CONTAINS to the repository.
    Filters can be combined: a file must satisfy all supplied constraints.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        prefix: Optional path prefix filter (e.g. ``"group_vars/"``).
        suffix: Optional path suffix filter (e.g. ``".yml"``).
        pattern: Optional regex matched against ``relative_path``.

    Returns:
        Sorted list of matching relative paths.
    """

    query = (
        "MATCH (r:Repository {id: $repo_id})-[:REPO_CONTAINS]->(f:File)\n"
        "WHERE ($prefix IS NULL OR f.relative_path STARTS WITH $prefix)\n"
        "  AND ($suffix IS NULL OR f.relative_path ENDS WITH $suffix)\n"
        "RETURN f.relative_path AS relative_path\n"
        "ORDER BY f.relative_path"
    )
    db_manager = get_db_manager(database)
    with db_manager.get_driver().session() as session:
        rows = session.run(
            query,
            repo_id=repo_id,
            prefix=prefix,
            suffix=suffix,
        ).data()
    paths = [str(row["relative_path"]) for row in rows if row.get("relative_path")]
    if pattern is None:
        return paths
    regex = re.compile(pattern)
    return [relative_path for relative_path in paths if regex.search(relative_path)]


def file_exists(database: Any, repo_id: str, relative_path: str) -> bool:
    """Check whether a specific file exists in the indexed repo.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative file path to check.

    Returns:
        ``True`` when the file node exists in the graph.
    """

    query = (
        "MATCH (r:Repository {id: $repo_id})"
        "-[:REPO_CONTAINS]->"
        "(f:File {relative_path: $relative_path})\n"
        "RETURN count(f) > 0 AS exists"
    )
    db_manager = get_db_manager(database)
    with db_manager.get_driver().session() as session:
        rows = session.run(query, repo_id=repo_id, relative_path=relative_path).data()
    if rows:
        return bool(rows[0].get("exists", False))
    return False


def read_file_content(database: Any, repo_id: str, relative_path: str) -> str | None:
    """Read a file's content from the Postgres content store.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative file path.

    Returns:
        Text content or ``None`` when unavailable.
    """

    result = content_queries.get_file_content(
        database, repo_id=repo_id, relative_path=relative_path
    )
    if result and result.get("available"):
        content = result.get("content")
        return content if isinstance(content, str) else None
    return None


def read_yaml_file(database: Any, repo_id: str, relative_path: str) -> dict | None:
    """Read and parse a YAML file from the content store.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative YAML file path.

    Returns:
        Parsed dict or ``None`` when unavailable or unparseable.
    """

    content = read_file_content(database, repo_id, relative_path)
    if content is None:
        return None
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError:
        logger.debug("Failed to parse YAML file %s in repo %s", relative_path, repo_id)
        return None
    return parsed if isinstance(parsed, dict) else None


def read_yaml_document(database: Any, repo_id: str, relative_path: str) -> Any | None:
    """Read and parse a YAML document of any type from the content store.

    Unlike :func:`read_yaml_file` which only returns dicts, this accepts any
    valid YAML document type (list, dict, scalar).  Useful for Ansible
    playbooks which are YAML lists.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative YAML file path.

    Returns:
        Parsed YAML value or ``None`` when unavailable or unparseable.
    """

    content = read_file_content(database, repo_id, relative_path)
    if content is None:
        return None
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        logger.debug("Failed to parse YAML file %s in repo %s", relative_path, repo_id)
        return None

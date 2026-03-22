"""Bundle import helpers for PlatformContextGraph bundles."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import (
    debug_log,
    info_logger,
    warning_logger,
)


class _BundleImportMixin:
    """Import-side helpers for ``PCGBundle``."""

    db_manager: Any

    def import_from_bundle(
        self,
        bundle_path: Path,
        clear_existing: bool = False,
        readonly: bool = False,
    ) -> tuple[bool, str]:
        """Import a ``.pcg`` bundle into the configured database.

        Args:
            bundle_path: Path to the bundle archive.
            clear_existing: Whether to clear existing graph data first.
            readonly: Reserved flag for future read-only mounting support.

        Returns:
            Tuple of success flag and human-readable message.
        """

        del readonly
        try:
            info_logger(f"Starting import from {bundle_path}")
            if not bundle_path.exists():
                return False, f"Bundle file not found: {bundle_path}"

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                with zipfile.ZipFile(bundle_path, "r") as bundle_zip:
                    bundle_zip.extractall(temp_path)

                is_valid, validation_msg = self._validate_bundle(temp_path)
                if not is_valid:
                    return False, f"Invalid bundle: {validation_msg}"

                metadata = json.loads((temp_path / "metadata.json").read_text())
                info_logger(f"Loading bundle: {metadata.get('repo', 'unknown')}")
                info_logger(f"Bundle version: {metadata.get('pcg_version', 'unknown')}")

                repo_name = metadata.get("repo", "unknown")
                repo_path = metadata.get("repo_path")

                if clear_existing:
                    info_logger("Clearing all existing graph data...")
                    self._clear_graph()
                elif self._check_existing_repository(repo_name, repo_path):
                    return (
                        False,
                        f"Repository '{repo_name}' already exists in the database. "
                        "Use clear_existing=True to replace it.",
                    )

                self._import_schema(temp_path / "schema.json")
                node_count = self._import_nodes(temp_path / "nodes.jsonl")
                edge_count = self._import_edges(temp_path / "edges.jsonl")

            success_msg = f"✅ Successfully imported {bundle_path.name}\n"
            success_msg += f"   Repository: {metadata.get('repo', 'unknown')}\n"
            success_msg += f"   Nodes: {node_count:,} | Edges: {edge_count:,}"
            info_logger(success_msg)
            return True, success_msg
        except Exception as exc:  # pragma: no cover - exercised through callers
            error_msg = f"Failed to import bundle: {exc}"
            warning_logger(error_msg)
            return False, error_msg

    def _validate_bundle(self, bundle_dir: Path) -> tuple[bool, str]:
        """Validate that a bundle directory has the expected files and metadata.

        Args:
            bundle_dir: Extracted bundle directory.

        Returns:
            Tuple of validity flag and validation message.
        """

        required_files = ["metadata.json", "schema.json", "nodes.jsonl", "edges.jsonl"]
        for file_name in required_files:
            if not (bundle_dir / file_name).exists():
                return False, f"Missing required file: {file_name}"

        try:
            metadata = json.loads((bundle_dir / "metadata.json").read_text())
            if "pcg_version" not in metadata:
                return False, "Invalid metadata: missing pcg_version"
        except json.JSONDecodeError as exc:
            return False, f"Invalid metadata.json: {exc}"

        return True, "Valid bundle"

    def _check_existing_repository(
        self,
        repo_name: str,
        repo_path: str | None,
    ) -> bool:
        """Return whether a repository already exists in the graph.

        Args:
            repo_name: Repository name to check.
            repo_path: Optional repository path to check.

        Returns:
            ``True`` when a matching repository already exists.
        """

        with self.db_manager.get_driver().session() as session:
            result = session.run(
                "MATCH (r:Repository {name: $name}) RETURN r LIMIT 1",
                name=repo_name,
            )
            if result.single():
                return True

            if repo_path:
                result = session.run(
                    "MATCH (r:Repository {path: $path}) RETURN r LIMIT 1",
                    path=repo_path,
                )
                if result.single():
                    return True
        return False

    def _delete_repository(self, repo_identifier: str) -> None:
        """Delete a repository and all of its graph-owned nodes.

        Args:
            repo_identifier: Repository name or path identifier.
        """

        with self.db_manager.get_driver().session() as session:
            result = session.run(
                """
                MATCH (r:Repository)
                WHERE r.name = $identifier OR r.path = $identifier
                RETURN r.path as path
                LIMIT 1
                """,
                identifier=repo_identifier,
            )
            record = result.single()
            if not record:
                warning_logger(f"Repository '{repo_identifier}' not found for deletion")
                return

            repo_path = record["path"]
            session.run(
                """
                MATCH (n)
                WHERE n.path STARTS WITH $repo_path
                DETACH DELETE n
                """,
                repo_path=repo_path,
            )
            session.run(
                """
                MATCH (r:Repository)
                WHERE r.path = $repo_path
                DELETE r
                """,
                repo_path=repo_path,
            )
            info_logger(f"Deleted repository: {repo_identifier}")

    def _clear_graph(self) -> None:
        """Remove every node and edge from the current graph."""

        with self.db_manager.get_driver().session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def _import_schema(self, schema_file: Path) -> None:
        """Import or validate schema metadata before graph import.

        Args:
            schema_file: Path to the serialized schema payload.
        """

        del schema_file
        debug_log("Schema import not yet implemented - relying on application schema")

    def _import_nodes(self, nodes_file: Path) -> int:
        """Import bundle nodes from JSONL.

        Args:
            nodes_file: Path to the node JSONL file.

        Returns:
            Number of imported nodes.
        """

        count = 0
        batch_size = 1000
        batch = []
        id_mapping: dict[str, str] = {}

        with self.db_manager.get_driver().session() as session:
            with nodes_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    node_data = json.loads(line)
                    labels = node_data.pop("_labels", [])
                    old_id = node_data.pop("_id", None)
                    node_data.pop("_element_id", None)
                    batch.append((labels, node_data, old_id))
                    if len(batch) >= batch_size:
                        count += self._import_node_batch(session, batch, id_mapping)
                        batch = []
                if batch:
                    count += self._import_node_batch(session, batch, id_mapping)

        self._id_mapping = id_mapping
        return count

    def _import_node_batch(
        self,
        session: Any,
        batch: list[tuple[list[str], dict[str, Any], str | None]],
        id_mapping: dict[str, str],
    ) -> int:
        """Import a batch of nodes into the graph backend.

        Args:
            session: Active database session.
            batch: Node batch payload.
            id_mapping: Mutable old-to-new ID mapping.

        Returns:
            Number of nodes processed.
        """

        id_function = self._get_id_function()
        for labels, properties, old_id in batch:
            if not labels:
                continue
            label_str = ":".join(labels)
            query = (
                f"CREATE (n:{label_str}) SET n = $props "
                f"RETURN {id_function}(n) as new_id"
            )
            result = session.run(query, props=properties)
            record = result.single()
            if record and old_id:
                id_mapping[old_id] = record["new_id"]
        return len(batch)

    def _import_edges(self, edges_file: Path) -> int:
        """Import bundle relationships from JSONL.

        Args:
            edges_file: Path to the edge JSONL file.

        Returns:
            Number of imported edges.
        """

        count = 0
        batch_size = 1000
        batch: list[dict[str, Any]] = []

        with self.db_manager.get_driver().session() as session:
            with edges_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    batch.append(json.loads(line))
                    if len(batch) >= batch_size:
                        count += self._import_edge_batch(session, batch)
                        batch = []
                if batch:
                    count += self._import_edge_batch(session, batch)
        return count

    def _import_edge_batch(self, session: Any, batch: list[dict[str, Any]]) -> int:
        """Import a batch of bundle relationships.

        Args:
            session: Active database session.
            batch: Relationship batch payload.

        Returns:
            Number of edges processed.
        """

        id_mapping = getattr(self, "_id_mapping", {})
        id_function = self._get_id_function()
        for edge in batch:
            old_from = edge.get("from")
            old_to = edge.get("to")
            rel_type = edge.get("type")
            properties = edge.get("properties", {})
            new_from = id_mapping.get(old_from)
            new_to = id_mapping.get(old_to)
            if not new_from or not new_to:
                warning_logger("Skipping edge: node IDs not found in mapping")
                continue

            query = f"""
                MATCH (a), (b)
                WHERE {id_function}(a) = $from_id AND {id_function}(b) = $to_id
                CREATE (a)-[r:{rel_type}]->(b)
                SET r = $props
            """
            session.run(query, from_id=new_from, to_id=new_to, props=properties)
        return len(batch)

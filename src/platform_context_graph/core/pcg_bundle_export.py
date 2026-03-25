"""Bundle export helpers for PlatformContextGraph bundles."""

from __future__ import annotations

import json
import subprocess
import tempfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from platform_context_graph.observability import get_observability
from platform_context_graph.utils.debug_log import error_logger, info_logger


class _BundleExportMixin:
    """Export-side helpers for ``PCGBundle``."""

    VERSION: str
    db_manager: Any

    def export_to_bundle(
        self,
        output_path: Path,
        repo_path: Path | None = None,
        include_stats: bool = True,
    ) -> tuple[bool, str]:
        """Export the current graph or repository slice to a ``.pcg`` bundle.

        Args:
            output_path: Destination path for the bundle.
            repo_path: Optional repository path to scope the export.
            include_stats: Whether to include generated graph statistics.

        Returns:
            Tuple of success flag and human-readable message.
        """

        try:
            info_logger(
                f"Starting export to {output_path}",
                event_name="bundle.export.started",
                extra_keys={"output_path": str(output_path)},
            )

            if not str(output_path).endswith(".pcg"):
                output_path = Path(f"{output_path}.pcg")

            with get_observability().start_span(
                "pcg.bundle.export",
                attributes={"pcg.bundle.output_path": str(output_path)},
            ):
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    metadata = self._extract_metadata(repo_path)
                    (temp_path / "metadata.json").write_text(
                        json.dumps(_json_ready(metadata), indent=2),
                        encoding="utf-8",
                    )

                    schema = self._extract_schema()
                    (temp_path / "schema.json").write_text(
                        json.dumps(_json_ready(schema), indent=2),
                        encoding="utf-8",
                    )

                    node_count = self._extract_nodes(
                        temp_path / "nodes.jsonl", repo_path
                    )
                    edge_count = self._extract_edges(
                        temp_path / "edges.jsonl", repo_path
                    )

                    stats: dict[str, Any] | None = None
                    if include_stats:
                        stats = self._generate_stats(repo_path, node_count, edge_count)
                        (temp_path / "stats.json").write_text(
                            json.dumps(_json_ready(stats), indent=2),
                            encoding="utf-8",
                        )

                    self._create_readme(temp_path / "README.md", metadata, stats)
                    self._create_zip(temp_path, output_path)

            success_msg = f"✅ Successfully exported to {output_path}\n"
            success_msg += f"   Nodes: {node_count:,} | Edges: {edge_count:,}"
            info_logger(
                success_msg,
                event_name="bundle.export.completed",
                extra_keys={
                    "output_path": str(output_path),
                    "node_count": node_count,
                    "edge_count": edge_count,
                },
            )
            return True, success_msg

        except Exception as exc:  # pragma: no cover - exercised through callers
            error_msg = f"Failed to export bundle: {exc}"
            error_logger(
                error_msg,
                event_name="bundle.export.failed",
                extra_keys={"output_path": str(output_path)},
                exc_info=exc,
            )
            traceback.print_exc()
            return False, error_msg

    def _extract_metadata(self, repo_path: Path | None) -> dict[str, Any]:
        """Extract repository and export metadata for the bundle.

        Args:
            repo_path: Optional repository path to scope the export.

        Returns:
            Metadata payload for ``metadata.json``.
        """

        metadata: dict[str, Any] = {
            "pcg_version": self.VERSION,
            "exported_at": datetime.now().isoformat(),
            "format_version": "1.0",
        }

        with self.db_manager.get_driver().session() as session:
            if repo_path:
                result = session.run(
                    "MATCH (r:Repository {path: $path}) RETURN r",
                    path=str(repo_path.resolve()),
                )
                repo_node = result.single()
                if repo_node:
                    node = repo_node["r"]
                    try:
                        repo = dict(node)
                    except TypeError:
                        repo = {}
                        if hasattr(node, "_properties"):
                            repo = dict(node._properties)
                        elif hasattr(node, "properties"):
                            repo = dict(node.properties)
                        else:
                            for attr in ["name", "path", "is_dependency"]:
                                if hasattr(node, attr):
                                    repo[attr] = getattr(node, attr)

                    metadata["repo"] = repo.get("name", str(repo_path))
                    metadata["repo_path"] = repo.get("path")
                    metadata["is_dependency"] = repo.get("is_dependency", False)
            else:
                result = session.run(
                    "MATCH (r:Repository) RETURN r.name as name, r.path as path"
                )
                repos = [
                    {"name": record["name"], "path": record["path"]}
                    for record in result
                ]
                metadata["repositories"] = repos
                metadata["repo"] = (
                    "multiple"
                    if len(repos) > 1
                    else repos[0]["name"] if repos else "unknown"
                )

            if repo_path and repo_path.exists():
                try:
                    commit = (
                        subprocess.check_output(
                            ["git", "rev-parse", "HEAD"],
                            cwd=repo_path,
                            stderr=subprocess.DEVNULL,
                        )
                        .decode()
                        .strip()
                    )
                    metadata["commit"] = commit[:8]

                    result = session.run(
                        """
                        MATCH (f:File)
                        WHERE f.path STARTS WITH $repo_path
                        RETURN f.language as language, count(*) as count
                        ORDER BY count DESC
                        """,
                        repo_path=str(repo_path.resolve()),
                    )
                    languages = {
                        record["language"]: record["count"]
                        for record in result
                        if record["language"]
                    }
                    metadata["languages"] = list(languages.keys())
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        return metadata

    def _extract_schema(self) -> dict[str, Any]:
        """Extract graph schema metadata for the bundle.

        Returns:
            Schema payload with labels, relationship types, constraints, and indexes.
        """

        schema = {
            "node_labels": [],
            "relationship_types": [],
            "constraints": [],
            "indexes": [],
        }

        with self.db_manager.get_driver().session() as session:
            try:
                result = session.run("CALL db.labels()")
                labels = []
                for record in result:
                    try:
                        labels.append(record[0])
                    except (KeyError, TypeError):
                        if hasattr(record, "values"):
                            values = list(record.values())
                            if values:
                                labels.append(values[0])
                schema["node_labels"] = labels
            except Exception:
                schema["node_labels"] = []

            try:
                result = session.run("CALL db.relationshipTypes()")
                rel_types = []
                for record in result:
                    try:
                        rel_types.append(record[0])
                    except (KeyError, TypeError):
                        if hasattr(record, "values"):
                            values = list(record.values())
                            if values:
                                rel_types.append(values[0])
                schema["relationship_types"] = rel_types
            except Exception:
                schema["relationship_types"] = []

            try:
                result = session.run("SHOW CONSTRAINTS")
                schema["constraints"] = [dict(record) for record in result]
            except Exception:
                pass

            try:
                result = session.run("SHOW INDEXES")
                schema["indexes"] = [dict(record) for record in result]
            except Exception:
                pass

        return schema

    def _extract_nodes(self, output_file: Path, repo_path: Path | None) -> int:
        """Write bundle node data to JSONL.

        Args:
            output_file: Destination JSONL file.
            repo_path: Optional repository path to scope the export.

        Returns:
            Number of exported nodes.
        """

        count = 0
        with self.db_manager.get_driver().session() as session:
            if repo_path:
                query = """
                    MATCH (n)
                    WHERE n.path STARTS WITH $repo_path OR n.path STARTS WITH $repo_path
                    RETURN n, labels(n) as labels
                """
                params = {"repo_path": str(repo_path.resolve())}
            else:
                query = "MATCH (n) RETURN n, labels(n) as labels"
                params = {}

            try:
                result = session.run(query, params)
            except TypeError:
                result = session.run(query)

            with output_file.open("w", encoding="utf-8") as handle:
                for record in result:
                    node = record["n"]
                    labels = record["labels"]
                    try:
                        node_dict = dict(node)
                    except TypeError:
                        node_dict = {}
                        if hasattr(node, "_properties"):
                            node_dict = dict(node._properties)
                        elif hasattr(node, "properties"):
                            node_dict = dict(node.properties)

                    node_dict["_labels"] = labels
                    if hasattr(node, "element_id"):
                        node_dict["_id"] = node.element_id
                    elif hasattr(node, "id"):
                        node_dict["_id"] = str(node.id)

                    handle.write(json.dumps(_json_ready(node_dict)) + "\n")
                    count += 1
        return count

    def _extract_edges(self, output_file: Path, repo_path: Path | None) -> int:
        """Write bundle relationship data to JSONL.

        Args:
            output_file: Destination JSONL file.
            repo_path: Optional repository path to scope the export.

        Returns:
            Number of exported edges.
        """

        count = 0
        with self.db_manager.get_driver().session() as session:
            if repo_path:
                query = """
                    MATCH (n)-[r]->(m)
                    WHERE (n.path STARTS WITH $repo_path OR n.path STARTS WITH $repo_path)
                       OR (m.path STARTS WITH $repo_path OR m.path STARTS WITH $repo_path)
                    RETURN n, r, m, type(r) as rel_type
                """
                params = {"repo_path": str(repo_path.resolve())}
            else:
                query = "MATCH (n)-[r]->(m) RETURN n, r, m, type(r) as rel_type"
                params = {}

            try:
                result = session.run(query, params)
            except TypeError:
                result = session.run(query)

            with output_file.open("w", encoding="utf-8") as handle:
                for record in result:
                    source = record["n"]
                    target = record["m"]
                    rel = record["r"]
                    rel_type = record["rel_type"]

                    from_id = (
                        source.element_id
                        if hasattr(source, "element_id")
                        else (
                            str(source.id) if hasattr(source, "id") else str(id(source))
                        )
                    )
                    to_id = (
                        target.element_id
                        if hasattr(target, "element_id")
                        else (
                            str(target.id) if hasattr(target, "id") else str(id(target))
                        )
                    )

                    try:
                        rel_props = dict(rel)
                    except TypeError:
                        rel_props = {}
                        if hasattr(rel, "_properties"):
                            rel_props = dict(rel._properties)
                        elif hasattr(rel, "properties"):
                            rel_props = dict(rel.properties)

                    edge_dict = {
                        "from": from_id,
                        "to": to_id,
                        "type": rel_type,
                        "properties": rel_props,
                    }
                    handle.write(json.dumps(_json_ready(edge_dict)) + "\n")
                    count += 1
        return count

    def _generate_stats(
        self,
        repo_path: Path | None,
        node_count: int,
        edge_count: int,
    ) -> dict[str, Any]:
        """Generate graph statistics for the bundle.

        Args:
            repo_path: Optional repository path to scope the export.
            node_count: Exported node count.
            edge_count: Exported edge count.

        Returns:
            Statistics payload for ``stats.json``.
        """

        stats = {
            "total_nodes": node_count,
            "total_edges": edge_count,
            "generated_at": datetime.now().isoformat(),
        }

        with self.db_manager.get_driver().session() as session:
            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] as label, count(*) as count
                ORDER BY count DESC
                """)
            stats["nodes_by_type"] = {
                record["label"]: record["count"] for record in result if record["label"]
            }

            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) as type, count(*) as count
                ORDER BY count DESC
                """)
            stats["edges_by_type"] = {
                record["type"]: record["count"] for record in result
            }

            if repo_path:
                result = session.run(
                    "MATCH (f:File) WHERE f.path STARTS WITH $repo_path RETURN count(f) as count",
                    repo_path=str(repo_path.resolve()),
                )
            else:
                result = session.run("MATCH (f:File) RETURN count(f) as count")

            file_count = result.single()
            stats["files"] = file_count["count"] if file_count else 0
        return stats

    def _create_readme(
        self,
        output_file: Path,
        metadata: dict[str, Any],
        stats: dict[str, Any] | None,
    ) -> None:
        """Create the human-readable bundle README.

        Args:
            output_file: Destination markdown file.
            metadata: Bundle metadata payload.
            stats: Optional bundle statistics payload.
        """

        readme_content = f"""# PlatformContextGraph Bundle

## Repository Information
- **Repository**: {metadata.get('repo', 'Unknown')}
- **Exported**: {metadata.get('exported_at', 'Unknown')}
- **PCG Version**: {metadata.get('pcg_version', 'Unknown')}
"""

        if "commit" in metadata:
            readme_content += f"- **Commit**: {metadata['commit']}\n"

        if "languages" in metadata:
            readme_content += f"- **Languages**: {', '.join(metadata['languages'])}\n"

        if stats:
            readme_content += f"""
## Statistics
- **Total Nodes**: {stats.get('total_nodes', 0):,}
- **Total Edges**: {stats.get('total_edges', 0):,}
- **Files**: {stats.get('files', 0):,}

### Nodes by Type
"""
            for label, count in stats.get("nodes_by_type", {}).items():
                readme_content += f"- {label}: {count:,}\n"

            readme_content += "\n### Edges by Type\n"
            for rel_type, count in stats.get("edges_by_type", {}).items():
                readme_content += f"- {rel_type}: {count:,}\n"

        readme_content += """
## Usage

Load this bundle with:
```bash
pcg load <bundle-file>.pcg
```

Or import into existing graph:
```bash
pcg import <bundle-file>.pcg
```
"""

        output_file.write_text(readme_content, encoding="utf-8")

    def _create_zip(self, source_dir: Path, output_file: Path) -> None:
        """Create the final ZIP archive for the bundle.

        Args:
            source_dir: Temporary bundle directory.
            output_file: Final bundle archive path.
        """

        with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as bundle_zip:
            for path in source_dir.rglob("*"):
                if path.is_file():
                    bundle_zip.write(path, path.relative_to(source_dir))


def _json_ready(value: Any) -> Any:
    """Recursively normalize bundle payloads into JSON-serializable values."""

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except TypeError:
            pass
    return str(value)

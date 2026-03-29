"""Compatibility wrappers and translation helpers for the FalkorDB backend."""

from __future__ import annotations

import re

from platform_context_graph.utils.debug_log import error_logger


def apply_unix_socket_connection_patch() -> None:
    """Patch redis-py Unix socket connections to expose a `port` attribute.

    redis-py 5.x error telemetry expects every connection object to define
    `port`. `UnixDomainSocketConnection` does not, which can mask the original
    failure with a secondary `AttributeError`. Applying the patch at import time
    keeps FalkorDB startup errors readable.
    """
    try:
        from redis.connection import UnixDomainSocketConnection as uds_connection

        if not hasattr(uds_connection, "port"):
            uds_connection.port = 0  # type: ignore[attr-defined]
    except Exception:
        return


def translate_falkordb_schema_query(query: str) -> str:
    """Translate Neo4j schema statements into FalkorDB-compatible syntax.

    Args:
        query: Neo4j-flavored Cypher statement.

    Returns:
        FalkorDB-compatible Cypher.
    """
    q_upper = query.upper()

    if "CREATE FULLTEXT INDEX" in q_upper:
        return "RETURN 1"

    if "CREATE CONSTRAINT" in q_upper:
        query = re.sub(r"\s+IF NOT EXISTS", "", query, flags=re.IGNORECASE)

        match_node = re.search(r"FOR\s+(\([^)]+\))", query, flags=re.IGNORECASE)
        match_props_composite = re.search(
            r"REQUIRE\s+(\([^)]+\))\s+IS (?:UNIQUE|NODE KEY)",
            query,
            flags=re.IGNORECASE,
        )
        if match_node and match_props_composite:
            return (
                f"CREATE INDEX FOR {match_node.group(1)} "
                f"ON {match_props_composite.group(1)}"
            )

        match_prop_single = re.search(
            r"REQUIRE\s+(\S+)\s+IS UNIQUE", query, flags=re.IGNORECASE
        )
        if match_node and match_prop_single:
            return f"CREATE INDEX FOR {match_node.group(1)} ON ({match_prop_single.group(1)})"

        query = re.sub(
            r"CREATE CONSTRAINT\s+\w+\s+",
            "CREATE CONSTRAINT ",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(r"\s+FOR\s+", " ON ", query, flags=re.IGNORECASE)
        query = re.sub(r"\s+REQUIRE\s+", " ASSERT ", query, flags=re.IGNORECASE)
        return query

    if "CREATE INDEX" in q_upper:
        query = re.sub(r"\s+IF NOT EXISTS", "", query, flags=re.IGNORECASE)
        return re.sub(
            r"CREATE INDEX\s+\w+\s+FOR",
            "CREATE INDEX FOR",
            query,
            flags=re.IGNORECASE,
        )

    return query


class FalkorDBDriverWrapper:
    """Provide a Neo4j-like driver interface over a FalkorDB graph."""

    def __init__(self, graph):
        """Store the selected FalkorDB graph.

        Args:
            graph: Active FalkorDB graph handle.
        """
        self.graph = graph

    def session(self) -> "FalkorDBSessionWrapper":
        """Return a Neo4j-style session wrapper."""
        return FalkorDBSessionWrapper(self.graph)

    def close(self) -> None:
        """Provide a Neo4j-compatible no-op close method."""


class FalkorDBSessionWrapper:
    """Provide a Neo4j-like session interface over a FalkorDB graph."""

    def __init__(self, graph):
        """Store the selected FalkorDB graph.

        Args:
            graph: Active FalkorDB graph handle.
        """
        self.graph = graph

    def run(self, query: str, *args, **parameters) -> "FalkorDBResultWrapper":
        """Execute a Cypher query on FalkorDB.

        Args:
            query: Cypher query to execute.
            *args: Optional Neo4j-style positional parameter mapping.
            **parameters: Query parameters referenced by the statement.

        Returns:
            Wrapped FalkorDB result object.
        """
        translated_query = self._translate_schema_query(query)
        normalized_parameters = _normalize_run_parameters(args, parameters)
        try:
            result = self.graph.query(translated_query, normalized_parameters)
            return FalkorDBResultWrapper(result)
        except Exception as exc:
            error_msg = str(exc).lower()
            if (
                "already exists" in error_msg
                or "already created" in error_msg
                or "invalid constraint" in error_msg
            ):
                return FalkorDBResultWrapper(None)

            error_logger(
                f"FalkorDB query failed: {translated_query[:200]}... Error: {exc}"
            )
            raise

    def _translate_schema_query(self, query: str) -> str:
        """Translate schema-specific Neo4j Cypher to FalkorDB syntax."""
        return translate_falkordb_schema_query(query)

    def __enter__(self) -> "FalkorDBSessionWrapper":
        """Return the session wrapper for context-manager usage."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Provide a no-op context-manager exit hook."""


def _normalize_run_parameters(
    args: tuple[object, ...], parameters: dict[str, object]
) -> dict[str, object]:
    """Normalize Neo4j-style positional/keyword query parameters."""

    if len(args) > 1:
        raise TypeError("run() accepts at most one positional parameter mapping")

    normalized: dict[str, object] = {}
    if args:
        positional = args[0]
        if not isinstance(positional, dict):
            raise TypeError("run() positional parameters must be provided as a mapping")
        normalized.update(positional)

    parameters_mapping = parameters.pop("parameters", None)
    if parameters_mapping is not None:
        if not isinstance(parameters_mapping, dict):
            raise TypeError("run() parameters= value must be provided as a mapping")
        normalized.update(parameters_mapping)

    normalized.update(parameters)
    return normalized


class FalkorDBRecord(dict):
    """Provide a `.data()` method on top of a dict row for compatibility."""

    def data(self):
        """Return the record contents as a plain dictionary."""
        return self


class FalkorDBResultWrapper:
    """Provide a Neo4j-like result interface over FalkorDB results."""

    def __init__(self, result):
        """Store the raw FalkorDB result object.

        Args:
            result: Raw FalkorDB result returned by the client.
        """
        self.result = result
        self._consumed = False

    def consume(self) -> "FalkorDBResultWrapper":
        """Mark the result as consumed for compatibility with Neo4j APIs."""
        self._consumed = True
        return self

    def single(self) -> FalkorDBRecord | None:
        """Return the first wrapped record, if present."""
        data = self.data()
        return data[0] if data else None

    def data(self) -> list[FalkorDBRecord]:
        """Return all results as wrapped record dictionaries."""
        if not hasattr(self.result, "result_set"):
            return []

        results: list[FalkorDBRecord] = []
        if hasattr(self.result, "header") and self.result.header:
            headers = self.result.header
            for row in self.result.result_set:
                row_dict = FalkorDBRecord()
                for index, header in enumerate(headers):
                    if index >= len(row):
                        continue

                    if isinstance(header, (list, tuple)) and len(header) > 1:
                        header_name = header[1]
                        if isinstance(header_name, bytes):
                            header_name = header_name.decode("utf-8")
                    else:
                        header_name = str(header)
                    row_dict[header_name] = row[index]
                results.append(row_dict)
            return results

        for row in self.result.result_set:
            if isinstance(row, (list, tuple)) and len(row) == 1:
                results.append(FalkorDBRecord({"value": row[0]}))
            else:
                results.append(FalkorDBRecord({"value": row}))
        return results

    def __iter__(self):
        """Iterate over wrapped records."""
        return iter(self.data())

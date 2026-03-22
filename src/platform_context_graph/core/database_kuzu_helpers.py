"""Compatibility wrappers and query translation helpers for the Kuzu backend."""

from __future__ import annotations

import json
import re
from typing import Any

from platform_context_graph.core.database_kuzu_schema import (
    KUZU_LABELS_TO_ESCAPE,
    KUZU_SCHEMA_MAP,
    KUZU_UID_MAP,
)
from platform_context_graph.utils.debug_log import (
    debug_log,
    error_logger,
    warning_logger,
)


def _expand_property_updates(
    query: str, parameters: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Expand `SET node += $props` into explicit property assignments.

    Args:
        query: Raw Cypher query to translate.
        parameters: Query parameter mapping.

    Returns:
        A tuple containing the translated query and filtered parameters.
    """
    if "SET" not in query or "+=" not in query:
        return query, parameters

    match = re.search(r"SET\s+(\w+)\s*\+=\s*\$(\w+)", query)
    if match is None:
        return query, parameters

    node_var = match.group(1)
    param_name = match.group(2)
    def_match = re.search(rf"\({node_var}:(\w+)", query)
    label = def_match.group(1) if def_match else None

    props_dict = parameters.get(param_name, {})
    if not isinstance(props_dict, dict):
        return query, parameters

    allowed_props = KUZU_SCHEMA_MAP.get(label, set()) if label else None
    set_clauses: list[str] = []
    new_params = parameters.copy()

    for key, value in props_dict.items():
        if isinstance(value, (dict, list)) and key not in {"args", "decorators"}:
            continue
        if allowed_props and key not in allowed_props:
            continue

        clean_key = f"{param_name}_{key}"
        set_clauses.append(f"{node_var}.{key} = ${clean_key}")
        new_params[clean_key] = value

    if set_clauses:
        query = query.replace(match.group(0), "SET " + ", ".join(set_clauses))
        new_params.pop(param_name, None)
        return query, new_params

    return query.replace(match.group(0), ""), parameters


def _inject_merge_uids(
    query: str, parameters: dict[str, Any], uid_map: dict[str, list[str]]
) -> tuple[str, dict[str, Any]]:
    """Add derived `uid` fields to MERGE blocks that need composite keys.

    Args:
        query: Raw Cypher query to translate.
        parameters: Query parameter mapping.
        uid_map: Mapping of labels to the parameter names that compose their UID.

    Returns:
        A tuple containing the translated query and updated parameters.
    """
    merge_pattern = r"MERGE\s+\((\w+):([^\s\{]+)\s*\{([^}]+)\}\)"
    translated_query = query
    translated_parameters = parameters.copy()

    for match in re.finditer(merge_pattern, query):
        var_name, label_raw, props_str = match.groups()
        label = label_raw.strip("`").strip(":")
        pk_parts = uid_map.get(label)
        if pk_parts is None:
            continue

        uid_parts: list[str] = []
        for part in pk_parts:
            param_match = re.search(rf"{part}:\s*\$(\w+)", props_str)
            if param_match is None:
                uid_parts = []
                break

            param_value = translated_parameters.get(param_match.group(1))
            if param_value is None:
                uid_parts = []
                break

            uid_parts.append(str(param_value))

        if not uid_parts:
            continue

        uid_param = f"__uid_{var_name}"
        old_block = f"{{{props_str}}}"
        new_block = f"{{{props_str}, uid: ${uid_param}}}"
        if old_block in translated_query:
            translated_query = translated_query.replace(old_block, new_block)
        else:
            warning_logger(
                "Kuzu UID injection: could not find props block in query for "
                f"label '{label}'"
            )

        translated_parameters[uid_param] = "".join(uid_parts)

    return translated_query, translated_parameters


def _escape_reserved_labels(query: str) -> str:
    """Escape Kuzu keywords that appear as labels or relationship types.

    Args:
        query: Query text to sanitize.

    Returns:
        The translated query text.
    """
    for label in KUZU_LABELS_TO_ESCAPE:
        query = re.sub(rf":{label}\b", f":`{label}`", query)
    return query


def _translate_polymorphic_matches(query: str) -> str:
    """Translate Neo4j-style OR label predicates into Kuzu label checks.

    Args:
        query: Query text to translate.

    Returns:
        The translated query text.
    """

    def poly_replacer(match: re.Match[str]) -> str:
        """Rewrite a label OR chain into a `label(var) IN [...]` predicate."""
        full_match = match.group(0)
        var_name = match.group(1)
        labels = re.findall(rf"{var_name}:([a-zA-Z0-9_]+)", full_match)
        return f"label({var_name}) IN {json.dumps(labels)}"

    return re.sub(
        r"\((\w+):[a-zA-Z0-9_]+(?:\s+OR\s+\1:[a-zA-Z0-9_]+)+\)",
        poly_replacer,
        query,
    )


def _translate_label_predicates(query: str) -> str:
    """Translate `WHERE n:Label` predicates to the Kuzu label function.

    Args:
        query: Query text to translate.

    Returns:
        The translated query text.
    """

    def single_label_replacer(match: re.Match[str]) -> str:
        """Rewrite a single label predicate into `label(var) = 'Label'`."""
        prefix = match.group(1)
        var_name = match.group(2)
        label = match.group(3)
        return f"{prefix}label({var_name}) = '{label}'"

    return re.sub(
        r"(WHERE\s+|AND\s+|OR\s+)(\w+):([a-zA-Z0-9_]+)",
        single_label_replacer,
        query,
        flags=re.IGNORECASE,
    )


def translate_kuzu_query(
    query: str,
    parameters: dict[str, Any],
    uid_map: dict[str, list[str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Translate Neo4j-flavored Cypher into Kuzu-compatible Cypher.

    Args:
        query: Raw Cypher query to translate.
        parameters: Query parameters referenced by the Cypher.
        uid_map: Optional override for composite UID definitions.

    Returns:
        The translated query string and the filtered parameter mapping.
    """
    translated_query = query
    translated_parameters = parameters.copy()

    translated_query, translated_parameters = _expand_property_updates(
        translated_query, translated_parameters
    )
    translated_query, translated_parameters = _inject_merge_uids(
        translated_query, translated_parameters, uid_map or KUZU_UID_MAP
    )
    translated_query = _escape_reserved_labels(translated_query)
    translated_query = translated_query.replace("labels(n)[0]", "label(n)")
    translated_query = _translate_polymorphic_matches(translated_query)
    translated_query = _translate_label_predicates(translated_query)
    translated_query = translated_query.replace("coalesce(", "COALESCE(")

    if any(
        token in translated_query.upper()
        for token in ["CREATE CONSTRAINT", "CREATE INDEX"]
    ):
        return "RETURN 1", {}

    used_params = set(re.findall(r"\$(\w+)", translated_query))
    translated_parameters = {
        key: value for key, value in translated_parameters.items() if key in used_params
    }
    return translated_query, translated_parameters


class KuzuDriverWrapper:
    """Provide a Neo4j-like driver interface over a Kuzu connection."""

    def __init__(self, conn):
        """Store the active Kuzu connection.

        Args:
            conn: Kuzu connection object returned by the backend driver.
        """
        self.conn = conn

    def session(self) -> "KuzuSessionWrapper":
        """Return a session wrapper for the underlying connection."""
        return KuzuSessionWrapper(self.conn)

    def close(self) -> None:
        """Provide a Neo4j-compatible close method for callers."""


class KuzuSessionWrapper:
    """Provide a Neo4j-like session interface over a Kuzu connection."""

    def __init__(self, conn):
        """Initialize the wrapper with the active Kuzu connection.

        Args:
            conn: Kuzu connection object returned by the backend driver.
        """
        self.conn = conn
        self.uid_map = KUZU_UID_MAP

    def __enter__(self) -> "KuzuSessionWrapper":
        """Return the session wrapper for context-manager usage."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit the context manager without suppressing exceptions.

        Args:
            exc_type: Exception type if one was raised.
            exc_val: Exception instance if one was raised.
            exc_tb: Traceback if one was raised.

        Returns:
            `False` so exceptions propagate to the caller.
        """
        return False

    def run(self, query: str, *args, **parameters) -> "KuzuResultWrapper":
        """Execute a translated query and wrap the result.

        Args:
            query: Cypher query to run.
            *args: Optional Neo4j-style positional parameter mapping.
            **parameters: Query parameters referenced by the Cypher.

        Returns:
            Wrapped Kuzu result object.
        """
        debug_log(f"Original Query: {query[:200]}")
        normalized_parameters = _normalize_run_parameters(args, parameters)
        translated_query, translated_params = self._translate_query(
            query, normalized_parameters
        )
        debug_log(f"Translated Query: {translated_query[:200]}")
        try:
            result = self.conn.execute(translated_query, translated_params)
            return KuzuResultWrapper(result)
        except Exception as exc:
            err_str = str(exc).lower()
            if "already exists" in err_str:
                return KuzuResultWrapper(None)
            error_logger(f"Kuzu Query failed: {query[:100]}... Error: {exc}")
            debug_log(f"Kuzu Query failed: {query[:100]}... Error: {exc}")
            raise

    def _translate_query(
        self, query: str, parameters: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Translate Neo4j Cypher to Kuzu Cypher.

        Args:
            query: Raw Cypher query to translate.
            parameters: Query parameter mapping.

        Returns:
            The translated query and filtered parameters.
        """
        return translate_kuzu_query(query, parameters, uid_map=self.uid_map)


def _normalize_run_parameters(
    args: tuple[Any, ...], parameters: dict[str, Any]
) -> dict[str, Any]:
    """Normalize Neo4j-style positional/keyword query parameters."""

    if len(args) > 1:
        raise TypeError("run() accepts at most one positional parameter mapping")

    normalized: dict[str, Any] = {}
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


class KuzuRecord:
    """Provide dict-like and index-based access for Kuzu result rows."""

    def __init__(self, data_dict: dict[str, Any]):
        """Store row data and preserve column order.

        Args:
            data_dict: Mapping of column names to row values.
        """
        self._data = data_dict
        self._keys = list(data_dict.keys())

    def data(self) -> dict[str, Any]:
        """Return the row as a plain dictionary."""
        return self._data

    def keys(self) -> list[str]:
        """Return the column names for the row."""
        return self._keys

    def items(self):
        """Return the row items."""
        return self._data.items()

    def values(self) -> list[Any]:
        """Return the row values in column order."""
        return list(self._data.values())

    def __len__(self) -> int:
        """Return the number of columns in the row."""
        return len(self._data)

    def __getitem__(self, key):
        """Support dict-style and index-style access to row data.

        Args:
            key: Column name or integer index.

        Returns:
            The requested row value.

        Raises:
            IndexError: If the integer index is out of range.
        """
        if isinstance(key, int):
            if 0 <= key < len(self._keys):
                return self._data[self._keys[key]]
            raise IndexError(f"Index {key} out of range")
        return self._data[key]

    def get(self, key, default=None):
        """Return a column value with an optional default."""
        return self._data.get(key, default)


class KuzuResultWrapper:
    """Provide a Neo4j-like result interface over a Kuzu result set."""

    def __init__(self, result):
        """Store the raw result object.

        Args:
            result: Raw result object returned by Kuzu.
        """
        self.result = result
        self._consumed = False

    def consume(self) -> "KuzuResultWrapper":
        """Mark the result as consumed for compatibility with Neo4j APIs."""
        self._consumed = True
        return self

    def single(self) -> KuzuRecord | None:
        """Return the first record from the result set, if any."""
        records = self.data_raw()
        return KuzuRecord(records[0]) if records else None

    def data_raw(self) -> list[dict[str, Any]]:
        """Return all rows as plain dictionaries."""
        if not self.result:
            return []

        records: list[dict[str, Any]] = []
        columns = self.result.get_column_names()
        while self.result.has_next():
            row = self.result.get_next()
            record: dict[str, Any] = {}
            for index, value in enumerate(row):
                processed_value = value
                try:
                    if hasattr(value, "__class__") and "Node" in str(value.__class__):
                        processed_value = value
                        if not hasattr(processed_value, "labels"):
                            processed_value.labels = [value.get_label_name()]
                        if not hasattr(processed_value, "id"):
                            props = value.get_properties()
                            processed_value.id = props.get(
                                "uid", props.get("path", str(id(value)))
                            )
                        if not hasattr(processed_value, "properties"):
                            processed_value.properties = value.get_properties()
                    elif hasattr(value, "__class__") and "Rel" in str(value.__class__):
                        processed_value = value
                        if not hasattr(processed_value, "type"):
                            processed_value.type = value.get_label_name()
                        if not hasattr(processed_value, "src_node"):
                            processed_value.src_node = value.get_src_id()["offset"]
                        if not hasattr(processed_value, "dest_node"):
                            processed_value.dest_node = value.get_dst_id()["offset"]
                        if not hasattr(processed_value, "properties"):
                            processed_value.properties = value.get_properties()
                except Exception:
                    pass

                record[columns[index]] = processed_value
            records.append(record)
        return records

    def data(self) -> list[dict[str, Any]]:
        """Return all rows as plain dictionaries."""
        return self.data_raw()

    def __iter__(self):
        """Iterate over wrapped records."""
        return iter([KuzuRecord(record) for record in self.data_raw()])

"""SQL relationship materialization helpers."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

_CONTENT_ENTITY_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sql_tables", ("SqlTable",)),
    ("sql_columns", ("SqlColumn",)),
    ("sql_views", ("SqlView",)),
    ("sql_functions", ("SqlFunction",)),
    ("sql_triggers", ("SqlTrigger",)),
    ("sql_indexes", ("SqlIndex",)),
    ("classes", ("Class",)),
    ("functions", ("Function",)),
)
_RELATIONSHIP_SOURCE_KINDS = {
    "HAS_COLUMN": ("SqlTable",),
    "REFERENCES_TABLE": ("SqlTable",),
    "READS_FROM": ("SqlView", "SqlFunction"),
    "TRIGGERS_ON": ("SqlTrigger",),
    "EXECUTES": ("SqlTrigger",),
    "INDEXES": ("SqlIndex",),
}
_RELATIONSHIP_TARGET_KINDS = {
    "HAS_COLUMN": ("SqlColumn",),
    "REFERENCES_TABLE": ("SqlTable",),
    "READS_FROM": ("SqlTable", "SqlView"),
    "TRIGGERS_ON": ("SqlTable",),
    "EXECUTES": ("SqlFunction",),
    "INDEXES": ("SqlTable",),
}


def create_all_sql_links(
    builder_or_session: Any,
    all_file_data: Iterable[dict[str, Any]],
    *,
    info_logger_fn: Any | None = None,
) -> dict[str, int]:
    """Create SQL relationship edges after indexing completes."""

    file_data_list = list(all_file_data)
    if not _has_sql_relationship_work(file_data_list):
        return {}

    metrics: dict[str, int] = defaultdict(int)

    if callable(getattr(builder_or_session, "run", None)):
        entity_lookup = _build_entity_lookup(builder_or_session, file_data_list)
        _materialize_sql_links(
            builder_or_session,
            file_data_list,
            entity_lookup,
            metrics,
        )
    elif callable(getattr(getattr(builder_or_session, "driver", None), "session", None)):
        with builder_or_session.driver.session() as session:
            entity_lookup = _build_entity_lookup(session, file_data_list)
            _materialize_sql_links(session, file_data_list, entity_lookup, metrics)
    else:
        entity_lookup = _build_entity_lookup(builder_or_session, file_data_list)
        _materialize_sql_links(
            builder_or_session,
            file_data_list,
            entity_lookup,
            metrics,
        )

    if callable(info_logger_fn) and metrics:
        summary = ", ".join(f"{key}={value}" for key, value in sorted(metrics.items()))
        info_logger_fn(f"SQL relationship materialization: {summary}")
    return dict(metrics)


def _has_sql_relationship_work(file_data_list: list[dict[str, Any]]) -> bool:
    """Return whether any parsed files contain SQL relationship work."""

    return any(
        file_data.get("sql_relationships")
        or file_data.get("sql_migrations")
        or file_data.get("orm_table_mappings")
        or file_data.get("embedded_sql_queries")
        for file_data in file_data_list
    )


def _build_entity_lookup(
    session: Any,
    file_data_list: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    """Return entity-name lookup tables grouped by graph kind."""

    lookup: dict[str, dict[str, str]] = defaultdict(dict)
    pending: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_keys: set[tuple[str, str, str, int]] = set()
    for file_data in file_data_list:
        file_path = str(Path(file_data["path"]).resolve())
        for bucket_name, kinds in _CONTENT_ENTITY_BUCKETS:
            for item in file_data.get(bucket_name, []):
                name = item.get("name")
                line_number = item.get("line_number")
                if not isinstance(name, str) or not isinstance(line_number, int):
                    continue
                uid = item.get("uid")
                for kind in kinds:
                    if isinstance(uid, str) and uid:
                        lookup[kind].setdefault(name, uid)
                        continue
                    dedupe_key = (kind, file_path, name, line_number)
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    pending[kind].append(
                        {
                            "file_path": file_path,
                            "name": name,
                            "line_number": line_number,
                        }
                    )

    for kind, rows in pending.items():
        for row in _lookup_uids_in_graph(session, kind, rows):
            name = row.get("name")
            uid = row.get("uid")
            if isinstance(name, str) and isinstance(uid, str) and uid:
                lookup[kind].setdefault(name, uid)
    return lookup


def _lookup_uids_in_graph(
    session: Any,
    kind: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve entity UIDs from persisted graph nodes when snapshots lack them."""

    if not rows:
        return []

    return session.run(
        f"""
        UNWIND $rows AS row
        MATCH (n:{kind})
        WHERE n.path = row.file_path
          AND n.name = row.name
          AND n.line_number = row.line_number
        RETURN row.name AS name, n.uid AS uid
        """,
        rows=rows,
    ).data()


def _materialize_sql_links(
    session: Any,
    file_data_list: list[dict[str, Any]],
    entity_lookup: dict[str, dict[str, str]],
    metrics: dict[str, int],
) -> None:
    """Materialize SQL relationship rows using one active session."""

    rows_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    migrate_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []

    for file_data in file_data_list:
        for item in file_data.get("sql_relationships", []):
            source_uid = _resolve_uid(
                entity_lookup,
                item.get("source_name"),
                _RELATIONSHIP_SOURCE_KINDS.get(item.get("type", ""), ()),
            )
            target_uid = _resolve_uid(
                entity_lookup,
                item.get("target_name"),
                _RELATIONSHIP_TARGET_KINDS.get(item.get("type", ""), ()),
            )
            if source_uid is None or target_uid is None:
                continue
            rows_by_type[item["type"]].append(
                {
                    "source_uid": source_uid,
                    "target_uid": target_uid,
                    "line_number": item.get("line_number"),
                }
            )

        for item in file_data.get("sql_migrations", []):
            target_uid = _resolve_uid(
                entity_lookup,
                item.get("target_name"),
                (item.get("target_kind"),),
            )
            if target_uid is None:
                continue
            migrate_rows.append(
                {
                    "file_path": str(Path(file_data["path"]).resolve()),
                    "target_uid": target_uid,
                    "line_number": item.get("line_number"),
                    "tool": item.get("tool"),
                }
            )

        for item in file_data.get("orm_table_mappings", []):
            source_uid = _resolve_uid(entity_lookup, item.get("class_name"), ("Class",))
            target_uid = _resolve_uid(
                entity_lookup,
                item.get("table_name"),
                ("SqlTable",),
            )
            if source_uid is None or target_uid is None:
                continue
            mapping_rows.append(
                {
                    "source_uid": source_uid,
                    "target_uid": target_uid,
                    "line_number": item.get("line_number"),
                    "framework": item.get("framework"),
                }
            )

        for item in file_data.get("embedded_sql_queries", []):
            source_uid = _resolve_uid(
                entity_lookup,
                item.get("function_name"),
                ("Function",),
            )
            target_uid = _resolve_uid(
                entity_lookup,
                item.get("table_name"),
                ("SqlTable",),
            )
            if source_uid is None or target_uid is None:
                continue
            query_rows.append(
                {
                    "source_uid": source_uid,
                    "target_uid": target_uid,
                    "line_number": item.get("line_number"),
                    "operation": item.get("operation"),
                    "api": item.get("api"),
                }
            )

    for relationship_type, rows in rows_by_type.items():
        _run_uid_relationship_query(session, relationship_type, rows)
        metrics[f"{relationship_type.lower()}_edges"] += len(rows)
    _run_migrates_query(session, migrate_rows)
    metrics["migrates_edges"] += len(migrate_rows)
    _run_uid_relationship_query(
        session,
        "MAPS_TO_TABLE",
        mapping_rows,
        ("framework",),
    )
    metrics["maps_to_table_edges"] += len(mapping_rows)
    _run_uid_relationship_query(
        session,
        "QUERIES_TABLE",
        query_rows,
        ("operation", "api"),
    )
    metrics["queries_table_edges"] += len(query_rows)


def _resolve_uid(
    entity_lookup: dict[str, dict[str, str]],
    entity_name: str | None,
    kinds: tuple[str | None, ...],
) -> str | None:
    """Return the UID for one entity name constrained to the allowed kinds."""

    if not isinstance(entity_name, str):
        return None
    for kind in kinds:
        if not kind:
            continue
        uid = entity_lookup.get(kind, {}).get(entity_name)
        if uid is not None:
            return uid
    return None


def _run_uid_relationship_query(
    session: Any,
    relationship_type: str,
    rows: list[dict[str, Any]],
    property_keys: tuple[str, ...] = (),
) -> None:
    """Run one UID-based relationship batch."""

    if not rows:
        return
    set_parts = [f"rel.{key} = row.{key}" for key in ("line_number", *property_keys)]
    set_clause = ", ".join(set_parts)
    result = session.run(
        f"""
        UNWIND $rows AS row
        MATCH (source {{uid: row.source_uid}})
        MATCH (target {{uid: row.target_uid}})
        MERGE (source)-[rel:{relationship_type}]->(target)
        SET {set_clause}
        """,
        rows=rows,
    )
    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()


def _run_migrates_query(session: Any, rows: list[dict[str, Any]]) -> None:
    """Run one ``MIGRATES`` edge batch from files to SQL entities."""

    if not rows:
        return
    result = session.run(
        """
        UNWIND $rows AS row
        MATCH (source:File {path: row.file_path})
        MATCH (target {uid: row.target_uid})
        MERGE (source)-[rel:MIGRATES]->(target)
        SET rel.line_number = row.line_number,
            rel.tool = row.tool
        """,
        rows=rows,
    )
    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()


__all__ = ["create_all_sql_links"]

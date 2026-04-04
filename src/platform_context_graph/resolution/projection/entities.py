"""Parsed-entity graph projection helpers driven by stored facts."""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from typing import Iterable

from platform_context_graph.facts.storage.models import FactRecordRow

from .common import run_write_query
from .common import validate_cypher_identifier
from .files import iter_file_facts
from .repositories import _normalized_fact_type

BuildEntityMergeStatementFn = Callable[..., tuple[str, dict[str, object]]]
CollectFileWriteDataFn = Callable[..., dict[str, object]]
FlushWriteBatchesFn = Callable[..., dict[str, object]]


def build_entity_merge_statement(
    *,
    label: str,
    item: dict[str, object],
    file_path: str,
    use_uid_identity: bool,
) -> tuple[str, dict[str, object]]:
    """Build the canonical entity merge query for one parsed entity fact."""

    del use_uid_identity
    validate_cypher_identifier(label)
    extra_keys = [key for key in item if key not in {"name", "line_number"}]
    for key in extra_keys:
        validate_cypher_identifier(key)

    params: dict[str, object] = {
        "file_path": file_path,
        "name": item["name"],
        "line_number": item["line_number"],
    }
    for key in extra_keys:
        params[key] = item[key]

    set_parts = [
        "n.name = $name",
        "n.path = $file_path",
        "n.line_number = $line_number",
    ]
    for key in extra_keys:
        set_parts.append(f"n.{key} = ${key}")

    query = f"""
        MATCH (f:File {{path: $file_path}})
        MERGE (n:{label} {{name: $name, path: $file_path, line_number: $line_number}})
        SET {", ".join(set_parts)}
        MERGE (f)-[:CONTAINS]->(n)
    """
    return query, params


def iter_parsed_entity_facts(
    fact_records: Iterable[FactRecordRow],
) -> list[FactRecordRow]:
    """Return parsed-entity facts in stable insertion order."""

    seen_fact_ids: set[str] = set()
    entity_facts: list[FactRecordRow] = []
    for fact_record in fact_records:
        if _normalized_fact_type(fact_record.fact_type) != "ParsedEntityObserved":
            continue
        if fact_record.fact_id in seen_fact_ids:
            continue
        seen_fact_ids.add(fact_record.fact_id)
        entity_facts.append(fact_record)
    return entity_facts


def project_parsed_entity_facts(
    tx: object,
    fact_records: Iterable[FactRecordRow],
    *,
    collect_file_write_data_fn: CollectFileWriteDataFn | None = None,
    flush_write_batches_fn: FlushWriteBatchesFn | None = None,
    build_entity_merge_statement_fn: BuildEntityMergeStatementFn = (
        build_entity_merge_statement
    ),
) -> int:
    """Project parsed entity facts into graph nodes contained by File nodes."""

    projected = 0
    del build_entity_merge_statement_fn
    projected_file_keys: set[tuple[str, str]] = set()
    for file_fact in iter_file_facts(fact_records):
        if not file_fact.relative_path:
            continue
        parsed_file_data = file_fact.payload.get("parsed_file_data")
        if not isinstance(parsed_file_data, dict):
            continue
        if collect_file_write_data_fn is None:
            from platform_context_graph.graph.persistence import collect_file_write_data

            collect_file_write_data_fn = collect_file_write_data
        if flush_write_batches_fn is None:
            from platform_context_graph.graph.persistence import flush_write_batches

            flush_write_batches_fn = flush_write_batches
        file_path = str(
            parsed_file_data.get("path")
            or (Path(file_fact.checkout_path) / file_fact.relative_path)
        )
        file_data = dict(parsed_file_data)
        file_data.setdefault("path", file_path)
        file_data.setdefault("repo_path", file_fact.checkout_path)
        file_data["is_dependency"] = bool(file_fact.payload.get("is_dependency", False))
        write_data = collect_file_write_data_fn(
            file_data,
            file_path,
            max_entity_value_length=None,
        )
        flush_write_batches_fn(tx, write_data)
        entity_rows = sum(
            len(rows) for rows in write_data.get("entities_by_label", {}).values()
        )
        projected += entity_rows
        projected_file_keys.add((file_fact.checkout_path, file_fact.relative_path))
    projected += _project_standalone_entity_facts(
        tx,
        iter_parsed_entity_facts(fact_records),
        projected_file_keys=projected_file_keys,
        flush_write_batches_fn=flush_write_batches_fn,
    )
    return projected


def _project_standalone_entity_facts(
    tx: object,
    fact_records: Iterable[FactRecordRow],
    *,
    projected_file_keys: set[tuple[str, str]],
    flush_write_batches_fn: FlushWriteBatchesFn | None = None,
) -> int:
    """Project parsed-entity facts that are not already in file payloads."""

    if flush_write_batches_fn is None:
        from platform_context_graph.graph.persistence import flush_write_batches

        flush_write_batches_fn = flush_write_batches

    from platform_context_graph.graph.persistence.batch_support import (
        empty_accumulator,
    )
    from platform_context_graph.graph.persistence.unwind import entity_props_for_unwind

    batches = empty_accumulator()
    projected = 0
    for fact_record in fact_records:
        if not fact_record.relative_path:
            continue
        if (
            fact_record.checkout_path,
            fact_record.relative_path,
        ) in projected_file_keys:
            continue
        file_path = str(
            Path(fact_record.checkout_path).resolve() / fact_record.relative_path
        )
        row = entity_props_for_unwind(
            str(fact_record.payload.get("entity_kind") or ""),
            {
                "name": str(fact_record.payload.get("entity_name") or ""),
                "line_number": int(fact_record.payload.get("start_line") or 0),
                "end_line": int(fact_record.payload.get("end_line") or 0),
                "lang": fact_record.payload.get("language"),
            },
            file_path,
            False,
        )
        label = str(fact_record.payload.get("entity_kind") or "")
        batches["entities_by_label"].setdefault(label, []).append(row)
        projected += 1

    if projected:
        flush_write_batches_fn(tx, batches)
    return projected


__all__ = [
    "_project_standalone_entity_facts",
    "build_entity_merge_statement",
    "iter_parsed_entity_facts",
    "project_parsed_entity_facts",
]

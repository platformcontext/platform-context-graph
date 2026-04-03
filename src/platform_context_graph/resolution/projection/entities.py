"""Parsed-entity graph projection helpers driven by stored facts."""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from typing import Iterable

from platform_context_graph.facts.storage.models import FactRecordRow

from .common import run_write_query
from .common import validate_cypher_identifier
from .repositories import _normalized_fact_type

BuildEntityMergeStatementFn = Callable[..., tuple[str, dict[str, object]]]


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
    build_entity_merge_statement_fn: BuildEntityMergeStatementFn = (
        build_entity_merge_statement
    ),
) -> int:
    """Project parsed entity facts into graph nodes contained by File nodes."""

    projected = 0
    for fact_record in iter_parsed_entity_facts(fact_records):
        if not fact_record.relative_path:
            continue
        file_path = str(
            Path(fact_record.checkout_path).resolve() / fact_record.relative_path
        )
        entity_payload = {
            "name": str(fact_record.payload.get("entity_name") or ""),
            "line_number": int(fact_record.payload.get("start_line") or 0),
            "end_line": int(fact_record.payload.get("end_line") or 0),
            "lang": fact_record.payload.get("language"),
        }
        query, params = build_entity_merge_statement_fn(
            label=str(fact_record.payload.get("entity_kind") or ""),
            item=entity_payload,
            file_path=file_path,
            use_uid_identity=False,
        )
        run_write_query(tx, query, **params)
        projected += 1
    return projected


__all__ = [
    "build_entity_merge_statement",
    "iter_parsed_entity_facts",
    "project_parsed_entity_facts",
]

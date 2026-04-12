"""dbt-style compiled SQL normalization for local replay fixtures."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_SELECT_CLAUSE_RE = re.compile(
    r"\bselect\b(?P<select>.*?)\bfrom\b", re.IGNORECASE | re.DOTALL
)
_AS_ALIAS_RE = re.compile(
    r"^(?P<expression>.+?)\s+as\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)$",
    re.IGNORECASE | re.DOTALL,
)
_QUALIFIED_REFERENCE_RE = re.compile(
    r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\."
    r"(?P<column>\*|[A-Za-z_][A-Za-z0-9_]*)(?=[^A-Za-z0-9_]|$)"
)
_FROM_SOURCE_RE = re.compile(
    r"\b(?:from|join|left\s+join|right\s+join|inner\s+join|full\s+join|cross\s+join)"
    r"\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,2})"
    r"\s+(?:as\s+)?(?P<alias>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _ProjectionLineage:
    """Normalized lineage extracted from one compiled SQL projection."""

    output_column: str | None
    source_columns: tuple[str, ...]
    unresolved_references: tuple[dict[str, str], ...]


class DbtCompiledSqlPlugin:
    """Normalize one dbt-style manifest into data-intelligence graph payloads."""

    name = "dbt-compiled-sql"
    category = "analytics"
    replay_fixture_groups = ("analytics_compiled_comprehensive",)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize a dbt manifest payload into vendor-neutral graph records."""

        sources = payload.get("sources", {})
        nodes = payload.get("nodes", {})
        output_assets: dict[str, dict[str, str]] = {}
        source_assets: dict[str, dict[str, str]] = {}
        data_columns: dict[str, dict[str, str]] = {}
        analytics_models: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        unresolved_references: list[dict[str, str]] = []

        for unique_id, source in sorted(sources.items()):
            asset = _asset_record(source)
            output_assets[unique_id] = asset
            source_assets[unique_id] = asset
            for column in _column_records_for_asset(source, asset["name"]).values():
                data_columns[column["name"]] = column

        for unique_id, node in sorted(nodes.items()):
            if node.get("resource_type") != "model":
                continue

            model_asset = _asset_record(node)
            output_assets[unique_id] = model_asset
            for column in _column_records_for_asset(node, model_asset["name"]).values():
                data_columns[column["name"]] = column

            compiled_sql = str(node.get("compiled_code", ""))
            alias_map = _extract_source_aliases(compiled_sql)
            model_unresolved: list[dict[str, str]] = []
            projection_count = 0

            relationships.append(
                {
                    "type": "COMPILES_TO",
                    "source_id": f"analytics-model:{unique_id}",
                    "source_name": str(node.get("name", unique_id)),
                    "target_id": model_asset["id"],
                    "target_name": model_asset["name"],
                    "confidence": 1.0,
                }
            )

            for dependency in _dependency_assets(
                node.get("depends_on", {}).get("nodes", []),
                output_assets=output_assets,
                source_assets=source_assets,
                all_nodes=nodes,
                all_sources=sources,
            ):
                relationships.append(
                    {
                        "type": "ASSET_DERIVES_FROM",
                        "source_id": model_asset["id"],
                        "source_name": model_asset["name"],
                        "target_id": dependency["id"],
                        "target_name": dependency["name"],
                        "confidence": 0.99,
                    }
                )

            for select_item in _extract_select_items(compiled_sql):
                projection_count += 1
                projection = _lineage_for_projection(
                    select_item=select_item,
                    alias_map=alias_map,
                    output_asset_name=model_asset["name"],
                    model_name=str(node.get("name", unique_id)),
                )
                model_unresolved.extend(projection.unresolved_references)

                if not projection.output_column:
                    continue

                output_column_name = (
                    f"{model_asset['name']}.{projection.output_column}"
                )
                data_columns.setdefault(
                    output_column_name,
                    {
                        "id": f"data-column:{output_column_name}",
                        "asset_name": model_asset["name"],
                        "name": output_column_name,
                        "line_number": int(node.get("line_number") or 1),
                    },
                )
                for source_column_name in projection.source_columns:
                    relationships.append(
                        {
                            "type": "COLUMN_DERIVES_FROM",
                            "source_id": f"data-column:{output_column_name}",
                            "source_name": output_column_name,
                            "target_id": f"data-column:{source_column_name}",
                            "target_name": source_column_name,
                            "confidence": 0.95,
                        }
                    )

            unresolved_references.extend(model_unresolved)
            analytics_models.append(
                {
                    "id": f"analytics-model:{unique_id}",
                    "name": str(node.get("name", unique_id)),
                    "asset_name": model_asset["name"],
                    "line_number": int(node.get("line_number") or 1),
                    "path": str(node.get("compiled_path") or node.get("path") or ""),
                    "materialization": str(
                        node.get("config", {}).get("materialized", "unknown")
                    ),
                    "parse_state": "partial" if model_unresolved else "complete",
                    "confidence": 0.5 if model_unresolved else 1.0,
                    "projection_count": projection_count,
                }
            )

        analytics_models.sort(key=lambda item: item["name"])
        data_assets = sorted(output_assets.values(), key=lambda item: item["name"])
        relationships.sort(
            key=lambda item: (item["type"], item["source_name"], item["target_name"])
        )

        return {
            "analytics_models": analytics_models,
            "data_assets": data_assets,
            "data_columns": sorted(data_columns.values(), key=lambda item: item["name"]),
            "relationships": relationships,
            "coverage": _coverage_summary(
                analytics_models=analytics_models,
                unresolved_references=unresolved_references,
            ),
        }


def _asset_record(node: Mapping[str, Any]) -> dict[str, str]:
    """Build one normalized asset record from a source or model node."""

    asset_name = _asset_name(node)
    return {
        "id": f"data-asset:{asset_name}",
        "name": asset_name,
        "line_number": int(node.get("line_number") or 1),
        "database": str(node.get("database") or ""),
        "schema": str(node.get("schema") or ""),
        "kind": str(node.get("resource_type") or "asset"),
    }


def _asset_name(node: Mapping[str, Any]) -> str:
    """Return the stable database.schema.object name for one manifest node."""

    relation_name = node.get("relation_name")
    if relation_name:
        return str(relation_name)

    database = str(node.get("database") or "").strip()
    schema = str(node.get("schema") or "").strip()
    identifier = str(
        node.get("identifier") or node.get("alias") or node.get("name") or ""
    ).strip()
    return ".".join(part for part in (database, schema, identifier) if part)


def _column_records_for_asset(
    node: Mapping[str, Any], asset_name: str
) -> dict[str, dict[str, str]]:
    """Build normalized column records from one manifest node definition."""

    columns = node.get("columns", {})
    records: dict[str, dict[str, str]] = {}
    for key, value in columns.items():
        column_name = str(value.get("name") or key)
        qualified_name = f"{asset_name}.{column_name}"
        records[qualified_name] = {
            "id": f"data-column:{qualified_name}",
            "asset_name": asset_name,
            "name": qualified_name,
            "line_number": int(node.get("line_number") or 1),
        }
    return records


def _dependency_assets(
    dependencies: Sequence[str],
    *,
    output_assets: Mapping[str, dict[str, str]],
    source_assets: Mapping[str, dict[str, str]],
    all_nodes: Mapping[str, Mapping[str, Any]],
    all_sources: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Resolve unique dependency assets from manifest dependency IDs."""

    assets: dict[str, dict[str, str]] = {}
    for dependency in dependencies:
        asset = output_assets.get(dependency) or source_assets.get(dependency)
        if asset is None:
            dependency_node = all_nodes.get(dependency) or all_sources.get(dependency)
            if dependency_node is None:
                continue
            asset = _asset_record(dependency_node)
        assets[asset["name"]] = asset
    return [assets[name] for name in sorted(assets)]


def _extract_select_items(compiled_sql: str) -> list[str]:
    """Extract top-level SELECT projections from compiled SQL text."""

    match = _SELECT_CLAUSE_RE.search(compiled_sql)
    if match is None:
        return []

    select_clause = match.group("select")
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_single_quote = False

    for character in select_clause:
        if character == "'" and (not current or current[-1] != "\\"):
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if character == "(":
                depth += 1
            elif character == ")" and depth > 0:
                depth -= 1
            elif character == "," and depth == 0:
                item = "".join(current).strip()
                if item:
                    items.append(item)
                current = []
                continue
        current.append(character)

    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _extract_source_aliases(compiled_sql: str) -> dict[str, str]:
    """Map SQL table aliases back to normalized asset names."""

    alias_map: dict[str, str] = {}
    for match in _FROM_SOURCE_RE.finditer(compiled_sql):
        table_name = match.group("table").strip()
        alias_map[match.group("alias").strip()] = table_name
    return alias_map


def _lineage_for_projection(
    *,
    select_item: str,
    alias_map: Mapping[str, str],
    output_asset_name: str,
    model_name: str,
) -> _ProjectionLineage:
    """Extract supported source-column lineage from one SELECT item."""

    match = _AS_ALIAS_RE.match(select_item.strip())
    if match:
        expression = match.group("expression").strip()
        output_column = match.group("alias").strip()
    else:
        expression = select_item.strip()
        output_column = _implicit_output_column(expression)

    source_columns: list[str] = []
    unresolved_references: list[dict[str, str]] = []
    seen_columns: set[str] = set()

    for reference in _QUALIFIED_REFERENCE_RE.finditer(expression):
        alias = reference.group("alias")
        column = reference.group("column")
        if column == "*":
            unresolved_references.append(
                {
                    "expression": f"{alias}.*",
                    "model_name": model_name,
                    "reason": "wildcard_projection_not_supported",
                }
            )
            continue

        source_asset_name = alias_map.get(alias)
        if source_asset_name is None:
            unresolved_references.append(
                {
                    "expression": f"{alias}.{column}",
                    "model_name": model_name,
                    "reason": "source_alias_not_resolved",
                }
            )
            continue

        qualified_source_column = f"{source_asset_name}.{column}"
        if qualified_source_column in seen_columns:
            continue
        seen_columns.add(qualified_source_column)
        source_columns.append(qualified_source_column)

    if output_column is None and source_columns:
        output_column = source_columns[0].rsplit(".", maxsplit=1)[-1]
    if output_column is not None:
        output_column = output_column.strip()

    return _ProjectionLineage(
        output_column=output_column,
        source_columns=tuple(source_columns),
        unresolved_references=tuple(unresolved_references),
    )


def _implicit_output_column(expression: str) -> str | None:
    """Infer an output column name when a projection omits `AS alias`."""

    references = list(_QUALIFIED_REFERENCE_RE.finditer(expression))
    if len(references) == 1 and references[0].group("column") != "*":
        return references[0].group("column")
    return None


def _coverage_summary(
    *,
    analytics_models: Sequence[Mapping[str, Any]],
    unresolved_references: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Summarize normalization confidence and unresolved lineage gaps."""

    if not analytics_models:
        return {
            "confidence": 0.0,
            "state": "failed",
            "unresolved_references": [],
        }

    mean_confidence = sum(float(item["confidence"]) for item in analytics_models) / len(
        analytics_models
    )
    return {
        "confidence": round(mean_confidence, 2),
        "state": "partial" if unresolved_references else "complete",
        "unresolved_references": list(unresolved_references),
    }


__all__ = ["DbtCompiledSqlPlugin"]

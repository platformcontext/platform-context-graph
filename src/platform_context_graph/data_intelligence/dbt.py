"""dbt-style compiled SQL normalization for local replay fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .dbt_sql_lineage import extract_compiled_model_lineage


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
        asset_columns: dict[str, tuple[str, ...]] = {}
        data_columns: dict[str, dict[str, str]] = {}
        analytics_models: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        unresolved_references: list[dict[str, str]] = []

        for unique_id, source in sorted(sources.items()):
            asset = _asset_record(source)
            output_assets[unique_id] = asset
            source_assets[unique_id] = asset
            asset_columns[asset["name"]] = _column_names_for_asset(source)
            for column in _column_records_for_asset(source, asset["name"]).values():
                data_columns[column["name"]] = column

        for unique_id, node in sorted(nodes.items()):
            if node.get("resource_type") != "model":
                continue

            model_asset = _asset_record(node)
            output_assets[unique_id] = model_asset
            asset_columns.setdefault(model_asset["name"], _column_names_for_asset(node))
            for column in _column_records_for_asset(node, model_asset["name"]).values():
                data_columns[column["name"]] = column

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

            model_lineage = extract_compiled_model_lineage(
                str(node.get("compiled_code", "")),
                model_name=str(node.get("name", unique_id)),
                relation_column_names=asset_columns,
            )
            model_column_names = list(_column_names_for_asset(node))
            model_unresolved = list(model_lineage.unresolved_references)

            for column_lineage in model_lineage.column_lineage:
                if column_lineage.output_column not in model_column_names:
                    model_column_names.append(column_lineage.output_column)
                output_column_name = (
                    f"{model_asset['name']}.{column_lineage.output_column}"
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
                for source_column_name in column_lineage.source_columns:
                    relationship = {
                        "type": "COLUMN_DERIVES_FROM",
                        "source_id": f"data-column:{output_column_name}",
                        "source_name": output_column_name,
                        "target_id": f"data-column:{source_column_name}",
                        "target_name": source_column_name,
                        "confidence": 0.95,
                    }
                    if column_lineage.transform_kind is not None:
                        relationship["transform_kind"] = column_lineage.transform_kind
                    if column_lineage.transform_expression is not None:
                        relationship["transform_expression"] = (
                            column_lineage.transform_expression
                        )
                    relationships.append(relationship)

            asset_columns[model_asset["name"]] = tuple(model_column_names)
            unresolved_references.extend(model_unresolved)
            unresolved_summary = _unresolved_reference_summary(model_unresolved)
            analytics_models.append(
                {
                    "id": f"analytics-model:{unique_id}",
                    "name": str(node.get("name", unique_id)),
                    "asset_name": model_asset["name"],
                    "line_number": int(node.get("line_number") or 1),
                    "path": str(node.get("compiled_path") or node.get("path") or ""),
                    "compiled_path": str(
                        node.get("compiled_path") or node.get("path") or ""
                    ),
                    "materialization": str(
                        node.get("config", {}).get("materialized", "unknown")
                    ),
                    "parse_state": "partial" if model_unresolved else "complete",
                    "confidence": 0.5 if model_unresolved else 1.0,
                    "projection_count": model_lineage.projection_count,
                    "unresolved_reference_count": unresolved_summary["count"],
                    "unresolved_reference_reasons": unresolved_summary["reasons"],
                    "unresolved_reference_expressions": unresolved_summary[
                        "expressions"
                    ],
                }
            )

        analytics_models.sort(key=lambda item: item["name"])
        relationships.sort(
            key=lambda item: (item["type"], item["source_name"], item["target_name"])
        )
        return {
            "analytics_models": analytics_models,
            "data_assets": sorted(output_assets.values(), key=lambda item: item["name"]),
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

    records: dict[str, dict[str, str]] = {}
    for key, value in node.get("columns", {}).items():
        column_name = str(value.get("name") or key)
        qualified_name = f"{asset_name}.{column_name}"
        records[qualified_name] = {
            "id": f"data-column:{qualified_name}",
            "asset_name": asset_name,
            "name": qualified_name,
            "line_number": int(node.get("line_number") or 1),
        }
    return records


def _column_names_for_asset(node: Mapping[str, Any]) -> tuple[str, ...]:
    """Return manifest-declared column names in stable order for one asset."""

    return tuple(
        str(value.get("name") or key) for key, value in node.get("columns", {}).items()
    )


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


def _unresolved_reference_summary(
    unresolved_references: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Return graph-safe unresolved-lineage fields for one analytics model."""

    reasons: list[str] = []
    expressions: list[str] = []
    seen_reasons: set[str] = set()
    seen_expressions: set[str] = set()

    for item in unresolved_references:
        reason = str(item.get("reason") or "").strip()
        expression = str(item.get("expression") or "").strip()
        if reason and reason not in seen_reasons:
            seen_reasons.add(reason)
            reasons.append(reason)
        if expression and expression not in seen_expressions:
            seen_expressions.add(expression)
            expressions.append(expression)

    return {
        "count": len(unresolved_references),
        "reasons": reasons,
        "expressions": expressions,
    }


__all__ = ["DbtCompiledSqlPlugin"]

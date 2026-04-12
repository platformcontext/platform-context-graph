"""UNWIND query helpers for batched Neo4j writes in the persistence layer."""

from __future__ import annotations

import re
import time
from typing import Any

from ...cli.config_manager import get_config_value

# ---------------------------------------------------------------------------
# Entity property normalisation
# ---------------------------------------------------------------------------

ITEM_MAPPINGS_KEYS: list[tuple[str, str]] = [
    ("functions", "Function"),
    ("classes", "Class"),
    ("traits", "Trait"),
    ("variables", "Variable"),
    ("interfaces", "Interface"),
    ("annotations", "Annotation"),
    ("macros", "Macro"),
    ("structs", "Struct"),
    ("enums", "Enum"),
    ("unions", "Union"),
    ("records", "Record"),
    ("properties", "Property"),
    ("k8s_resources", "K8sResource"),
    ("argocd_applications", "ArgoCDApplication"),
    ("argocd_applicationsets", "ArgoCDApplicationSet"),
    ("crossplane_xrds", "CrossplaneXRD"),
    ("crossplane_compositions", "CrossplaneComposition"),
    ("crossplane_claims", "CrossplaneClaim"),
    ("kustomize_overlays", "KustomizeOverlay"),
    ("helm_charts", "HelmChart"),
    ("helm_values", "HelmValues"),
    ("terraform_resources", "TerraformResource"),
    ("terraform_variables", "TerraformVariable"),
    ("terraform_outputs", "TerraformOutput"),
    ("terraform_modules", "TerraformModule"),
    ("terraform_data_sources", "TerraformDataSource"),
    ("terraform_providers", "TerraformProvider"),
    ("terraform_locals", "TerraformLocal"),
    ("terragrunt_configs", "TerragruntConfig"),
    ("cloudformation_resources", "CloudFormationResource"),
    ("cloudformation_parameters", "CloudFormationParameter"),
    ("cloudformation_outputs", "CloudFormationOutput"),
    ("sql_tables", "SqlTable"),
    ("sql_columns", "SqlColumn"),
    ("sql_views", "SqlView"),
    ("sql_functions", "SqlFunction"),
    ("sql_triggers", "SqlTrigger"),
    ("sql_indexes", "SqlIndex"),
    ("analytics_models", "AnalyticsModel"),
    ("data_assets", "DataAsset"),
    ("data_columns", "DataColumn"),
    ("query_executions", "QueryExecution"),
    ("dashboard_assets", "DashboardAsset"),
]

VALUE_TRUNCATION_MARKER = " [truncated]"
DEFAULT_MAX_ENTITY_VALUE_LENGTH = 200
CYPHER_PROPERTY_KEY_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_cypher_label(label: str) -> str:
    """Return a label only when it is safe to interpolate into Cypher."""

    if CYPHER_PROPERTY_KEY_PATTERN.fullmatch(label) is None:
        raise ValueError(f"Invalid Cypher label: {label}")
    return label


def validate_cypher_property_keys(keys: list[str]) -> list[str]:
    """Return property keys only when all are safe for Cypher interpolation."""

    invalid_keys = [
        key for key in keys if CYPHER_PROPERTY_KEY_PATTERN.fullmatch(key) is None
    ]
    if invalid_keys:
        raise ValueError(
            "Invalid Cypher property key(s): " + ", ".join(sorted(invalid_keys))
        )
    return keys


def _consume_write_result(result: Any) -> None:
    """Eagerly consume Neo4j write results to release transaction buffers."""

    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()


def _run_write_query(tx: Any, query: str, /, **parameters: Any) -> None:
    """Execute one write query and eagerly consume its result when supported."""

    _consume_write_result(tx.run(query, **parameters))


def resolve_max_entity_value_length(raw_value: str | None = None) -> int:
    """Return the configured entity value preview length."""

    configured = raw_value
    if configured is None:
        configured = get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
    try:
        return max(1, int(configured or DEFAULT_MAX_ENTITY_VALUE_LENGTH))
    except ValueError:
        return DEFAULT_MAX_ENTITY_VALUE_LENGTH


def cap_entity_value(
    value: Any,
    *,
    max_entity_value_length: int | None = None,
) -> Any:
    """Return a capped graph value preview while preserving non-string payloads."""

    if not isinstance(value, str):
        return value

    preview_limit = (
        resolve_max_entity_value_length()
        if max_entity_value_length is None
        else max_entity_value_length
    )
    if len(value) <= preview_limit:
        return value
    return f"{value[:preview_limit]}{VALUE_TRUNCATION_MARKER}"


def entity_props_for_unwind(
    label: str,
    item: dict[str, Any],
    file_path: str,
    use_uid_identity: bool,
    max_entity_value_length: int | None = None,
) -> dict[str, Any]:
    """Return a normalised property dict suitable for use in an UNWIND batch.

    All keys that could appear for any item of this label are present; missing
    values are ``None`` so the UNWIND rows have a uniform shape.

    Args:
        label: Graph label for the entity.
        item: Parsed entity payload.
        file_path: Absolute file path containing the entity.
        use_uid_identity: Whether to use UID-based identity for this item.

    Returns:
        Flat dict of all properties for this entity row.
    """
    props: dict[str, Any] = {
        "file_path": file_path,
        "name": item["name"] or "",
        "line_number": item["line_number"],
        "use_uid_identity": use_uid_identity,
        "uid": item.get("uid"),
    }
    # Properties that participate in NODE KEY constraints must never be null.
    _node_key_props = {"name", "kind", "function_line_number"}
    extra_keys = [k for k in item if k not in {"name", "line_number", "path"}]
    for key in extra_keys:
        val = item[key]
        if key == "value":
            val = cap_entity_value(val, max_entity_value_length=max_entity_value_length)
        if val is None and key in _node_key_props:
            val = ""
        props[key] = val
    return props


# ---------------------------------------------------------------------------
# UNWIND query runners
# ---------------------------------------------------------------------------


def run_entity_unwind(
    tx: Any,
    label: str,
    rows: list[dict[str, Any]],
) -> dict[str, float | int]:
    """Execute UNWIND merges for a list of entity property dicts.

    Entities are split into two groups and executed as separate UNWIND
    queries so Neo4j can use indexes directly on the MERGE clause:

    - UID-identity rows are merged by ``{uid: row.uid}``
    - Name-identity rows are merged by ``{name, path, line_number}``

    Args:
        tx: Neo4j transaction (or session) to run the query against.
        label: Node label for the MERGE clause.
        rows: List of property dicts built by ``entity_props_for_unwind``.
    """
    validate_cypher_label(label)
    if not rows:
        return {
            "total_rows": 0,
            "uid_rows": 0,
            "name_rows": 0,
            "duration_seconds": 0.0,
        }

    uid_rows: list[dict[str, Any]] = []
    name_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("use_uid_identity") and row.get("uid"):
            uid_rows.append(row)
        else:
            name_rows.append(row)

    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    reserved = {"file_path", "name", "line_number", "use_uid_identity", "uid"}
    extra_keys = sorted(all_keys - reserved)
    validate_cypher_property_keys(extra_keys)

    for row in rows:
        for key in extra_keys:
            if key not in row:
                row[key] = None

    unique_file_paths = {
        file_path
        for row in rows
        if isinstance((file_path := row.get("file_path")), str) and file_path
    }
    single_file_path = (
        next(iter(unique_file_paths)) if len(unique_file_paths) == 1 else None
    )

    started = time.perf_counter()
    set_parts = [
        "n.name = row.name",
        f"n.path = {'$file_path' if single_file_path else 'row.file_path'}",
        "n.line_number = row.line_number",
    ]
    for key in extra_keys:
        set_parts.append(f"n.`{key}` = row.`{key}`")
    set_clause = ", ".join(set_parts)

    if uid_rows:
        if single_file_path:
            _run_write_query(
                tx,
                f"""
                MATCH (f:File {{path: $file_path}})
                UNWIND $rows AS row
                MERGE (n:{label} {{uid: row.uid}})
                SET {set_clause}
                MERGE (f)-[:CONTAINS]->(n)
                """,
                rows=uid_rows,
                file_path=single_file_path,
            )
        else:
            _run_write_query(
                tx,
                f"""
                UNWIND $rows AS row
                MATCH (f:File {{path: row.file_path}})
                MERGE (n:{label} {{uid: row.uid}})
                SET {set_clause}
                MERGE (f)-[:CONTAINS]->(n)
                """,
                rows=uid_rows,
            )

    if name_rows:
        if single_file_path:
            _run_write_query(
                tx,
                f"""
                MATCH (f:File {{path: $file_path}})
                UNWIND $rows AS row
                MERGE (n:{label} {{name: row.name, path: $file_path, line_number: row.line_number}})
                SET {set_clause}
                MERGE (f)-[:CONTAINS]->(n)
                """,
                rows=name_rows,
                file_path=single_file_path,
            )
        else:
            _run_write_query(
                tx,
                f"""
                UNWIND $rows AS row
                MATCH (f:File {{path: row.file_path}})
                MERGE (n:{label} {{name: row.name, path: row.file_path, line_number: row.line_number}})
                SET {set_clause}
                MERGE (f)-[:CONTAINS]->(n)
                """,
                rows=name_rows,
            )

    return {
        "total_rows": len(rows),
        "uid_rows": len(uid_rows),
        "name_rows": len(name_rows),
        "duration_seconds": time.perf_counter() - started,
    }


def run_parameter_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge all function parameters collected from one or more files.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``func_name``, ``file_path``,
              ``line_number``, ``arg_name``.
    """
    if not rows:
        return
    _run_write_query(
        tx,
        """
        UNWIND $rows AS row
        MATCH (fn:Function {name: row.func_name, path: row.file_path, line_number: row.line_number})
        MERGE (p:Parameter {name: row.arg_name, path: row.file_path, function_line_number: row.line_number})
        MERGE (fn)-[:HAS_PARAMETER]->(p)
        """,
        rows=rows,
    )


def run_module_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge all module nodes collected from one or more files.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``name``, ``lang``.
    """
    if not rows:
        return
    _run_write_query(
        tx,
        """
        UNWIND $rows AS row
        MERGE (mod:Module {name: row.name})
        ON CREATE SET mod.lang = row.lang
        ON MATCH  SET mod.lang = coalesce(mod.lang, row.lang)
        """,
        rows=rows,
    )


def run_nested_function_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge CONTAINS edges between outer and inner functions.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``context``, ``file_path``, ``name``,
              ``line_number``.
    """
    if not rows:
        return
    _run_write_query(
        tx,
        """
        UNWIND $rows AS row
        MATCH (outer:Function {name: row.context, path: row.file_path})
        MATCH (inner:Function {name: row.name, path: row.file_path, line_number: row.line_number})
        MERGE (outer)-[:CONTAINS]->(inner)
        """,
        rows=rows,
    )


def run_class_function_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge CONTAINS edges between classes and their methods.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``class_name``, ``file_path``,
              ``func_name``, ``func_line``.
    """
    if not rows:
        return
    _run_write_query(
        tx,
        """
        UNWIND $rows AS row
        MATCH (c:Class {name: row.class_name, path: row.file_path})
        MATCH (fn:Function {name: row.func_name, path: row.file_path, line_number: row.func_line})
        MERGE (c)-[:CONTAINS]->(fn)
        """,
        rows=rows,
    )


def run_module_inclusion_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge INCLUDES edges between classes and included modules.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``class_name``, ``file_path``,
              ``module_name``.
    """
    if not rows:
        return
    _run_write_query(
        tx,
        """
        UNWIND $rows AS row
        MATCH (c:Class {name: row.class_name, path: row.file_path})
        MERGE (m:Module {name: row.module_name})
        MERGE (c)-[:INCLUDES]->(m)
        """,
        rows=rows,
    )


def run_js_import_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge JavaScript IMPORTS relationships.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``file_path``, ``module_name``,
              ``imported_name``, ``alias`` (nullable), ``imp_line`` (nullable).
    """
    if not rows:
        return
    _run_write_query(
        tx,
        """
        UNWIND $rows AS row
        MATCH (f:File {path: row.file_path})
        MERGE (m:Module {name: row.module_name})
        MERGE (f)-[r:IMPORTS]->(m)
        SET r.imported_name = row.imported_name,
            r.alias = CASE WHEN row.alias IS NOT NULL THEN row.alias ELSE r.alias END,
            r.line_number = CASE WHEN row.imp_line IS NOT NULL THEN row.imp_line ELSE r.line_number END
        """,
        rows=rows,
    )


def run_generic_import_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge non-JavaScript IMPORTS relationships.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``file_path``, ``module_name``,
              ``full_import_name`` (nullable), ``line_number_rel`` (nullable),
              ``alias_rel`` (nullable).
    """
    if not rows:
        return
    _run_write_query(
        tx,
        """
        UNWIND $rows AS row
        MATCH (f:File {path: row.file_path})
        MERGE (m:Module {name: row.module_name})
        SET m.full_import_name = CASE WHEN row.full_import_name IS NOT NULL THEN row.full_import_name ELSE m.full_import_name END
        MERGE (f)-[r:IMPORTS]->(m)
        SET r.line_number = CASE WHEN row.line_number_rel IS NOT NULL THEN row.line_number_rel ELSE r.line_number END,
            r.alias = CASE WHEN row.alias_rel IS NOT NULL THEN row.alias_rel ELSE r.alias END
        """,
        rows=rows,
    )


__all__ = [
    "ITEM_MAPPINGS_KEYS",
    "cap_entity_value",
    "entity_props_for_unwind",
    "resolve_max_entity_value_length",
    "run_class_function_unwind",
    "run_entity_unwind",
    "run_generic_import_unwind",
    "run_js_import_unwind",
    "run_module_inclusion_unwind",
    "run_module_unwind",
    "run_nested_function_unwind",
    "run_parameter_unwind",
    "validate_cypher_label",
    "validate_cypher_property_keys",
]

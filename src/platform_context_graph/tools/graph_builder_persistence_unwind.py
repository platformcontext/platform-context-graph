"""UNWIND query helpers for batched Neo4j writes in the persistence layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.ingest import CONTENT_ENTITY_LABELS


# ---------------------------------------------------------------------------
# Entity property normalisation
# ---------------------------------------------------------------------------

_ITEM_MAPPINGS_KEYS: list[tuple[str, str]] = [
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
    ("terragrunt_configs", "TerragruntConfig"),
    ("cloudformation_resources", "CloudFormationResource"),
    ("cloudformation_parameters", "CloudFormationParameter"),
    ("cloudformation_outputs", "CloudFormationOutput"),
]


def entity_props_for_unwind(
    label: str,
    item: dict[str, Any],
    file_path: str,
    use_uid_identity: bool,
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
        "name": item["name"],
        "line_number": item["line_number"],
        "use_uid_identity": use_uid_identity,
        "uid": item.get("uid"),
    }
    extra_keys = [k for k in item if k not in {"name", "line_number", "path"}]
    for key in extra_keys:
        props[key] = item[key]
    return props


# ---------------------------------------------------------------------------
# UNWIND query runners
# ---------------------------------------------------------------------------


def run_entity_unwind(
    tx: Any,
    label: str,
    rows: list[dict[str, Any]],
) -> None:
    """Execute one UNWIND merge for a list of entity property dicts.

    Entities that carry a ``uid`` and ``use_uid_identity=True`` are merged by
    uid; all others are merged by ``(name, path, line_number)``.

    Args:
        tx: Neo4j transaction (or session) to run the query against.
        label: Node label for the MERGE clause.
        rows: List of property dicts built by ``entity_props_for_unwind``.
    """
    if not rows:
        return

    all_keys: set[str] = set()
    for row in rows:
        all_keys.update(row.keys())
    reserved = {"file_path", "name", "line_number", "use_uid_identity", "uid"}
    extra_keys = sorted(all_keys - reserved)

    for row in rows:
        for key in extra_keys:
            if key not in row:
                row[key] = None
        if "uid" not in row:
            row["uid"] = None
        if "use_uid_identity" not in row:
            row["use_uid_identity"] = False

    set_parts = [
        "n.name = row.name",
        "n.path = row.file_path",
        "n.line_number = row.line_number",
    ]
    for key in extra_keys:
        set_parts.append(f"n.`{key}` = row.`{key}`")

    query = f"""
        UNWIND $rows AS row
        MATCH (f:File {{path: row.file_path}})
        FOREACH (_ IN CASE WHEN row.use_uid_identity AND row.uid IS NOT NULL THEN [1] ELSE [] END |
            MERGE (n:{label} {{uid: row.uid}})
            SET {", ".join(set_parts)}
            MERGE (f)-[:CONTAINS]->(n)
        )
        FOREACH (_ IN CASE WHEN NOT (row.use_uid_identity AND row.uid IS NOT NULL) THEN [1] ELSE [] END |
            MERGE (n:{label} {{name: row.name, path: row.file_path, line_number: row.line_number}})
            SET {", ".join(set_parts)}
            MERGE (f)-[:CONTAINS]->(n)
        )
    """
    tx.run(query, rows=rows)


def run_parameter_unwind(tx: Any, rows: list[dict[str, Any]]) -> None:
    """UNWIND-merge all function parameters collected from one or more files.

    Args:
        tx: Neo4j transaction (or session).
        rows: List of dicts with keys ``func_name``, ``file_path``,
              ``line_number``, ``arg_name``.
    """
    if not rows:
        return
    tx.run(
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
    tx.run(
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
    tx.run(
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
    tx.run(
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
    tx.run(
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
    tx.run(
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
    tx.run(
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


# ---------------------------------------------------------------------------
# Batch data collection
# ---------------------------------------------------------------------------


def collect_file_write_data(
    file_data: dict[str, Any],
    file_path_str: str,
) -> dict[str, Any]:
    """Return all write-batches for a single file, ready for UNWIND dispatch.

    No Neo4j I/O is performed; this is pure data transformation.

    Args:
        file_data: Parsed file payload.
        file_path_str: Resolved absolute file path string.

    Returns:
        Dict with keys ``entities_by_label``, ``params_rows``,
        ``module_rows``, ``nested_fn_rows``, ``class_fn_rows``,
        ``module_inclusion_rows``, ``js_import_rows``,
        ``generic_import_rows``.
    """
    entities_by_label: dict[str, list[dict[str, Any]]] = {}
    params_rows: list[dict[str, Any]] = []
    module_rows: list[dict[str, Any]] = []
    nested_fn_rows: list[dict[str, Any]] = []
    class_fn_rows: list[dict[str, Any]] = []
    module_inclusion_rows: list[dict[str, Any]] = []
    js_import_rows: list[dict[str, Any]] = []
    generic_import_rows: list[dict[str, Any]] = []

    for field_key, label in _ITEM_MAPPINGS_KEYS:
        for item in file_data.get(field_key, []):
            if label == "Function" and "cyclomatic_complexity" not in item:
                item["cyclomatic_complexity"] = 1

            use_uid = label in CONTENT_ENTITY_LABELS and bool(item.get("uid"))
            row = entity_props_for_unwind(label, item, file_path_str, use_uid)
            entities_by_label.setdefault(label, []).append(row)

            if label == "Function":
                for arg_name in item.get("args", []):
                    params_rows.append(
                        {
                            "func_name": item["name"],
                            "file_path": file_path_str,
                            "line_number": item["line_number"],
                            "arg_name": arg_name,
                        }
                    )

    for module_item in file_data.get("modules", []):
        module_rows.append({"name": module_item["name"], "lang": file_data.get("lang")})

    for item in file_data.get("functions", []):
        if item.get("context_type") == "function_definition":
            nested_fn_rows.append(
                {
                    "context": item["context"],
                    "file_path": file_path_str,
                    "name": item["name"],
                    "line_number": item["line_number"],
                }
            )

    for func in file_data.get("functions", []):
        if func.get("class_context"):
            class_fn_rows.append(
                {
                    "class_name": func["class_context"],
                    "file_path": file_path_str,
                    "func_name": func["name"],
                    "func_line": func["line_number"],
                }
            )

    for inclusion in file_data.get("module_inclusions", []):
        module_inclusion_rows.append(
            {
                "class_name": inclusion["class"],
                "file_path": file_path_str,
                "module_name": inclusion["module"],
            }
        )

    lang = file_data.get("lang")
    for imp in file_data.get("imports", []):
        if lang == "javascript":
            module_name = imp.get("source")
            if not module_name:
                continue
            js_import_rows.append(
                {
                    "file_path": file_path_str,
                    "module_name": module_name,
                    "imported_name": imp.get("name", "*"),
                    "alias": imp.get("alias"),
                    "imp_line": imp.get("line_number"),
                }
            )
        else:
            generic_import_rows.append(
                {
                    "file_path": file_path_str,
                    "module_name": imp.get("name"),
                    "full_import_name": imp.get("full_import_name"),
                    "line_number_rel": imp.get("line_number") or None,
                    "alias_rel": imp.get("alias") or None,
                }
            )

    return {
        "entities_by_label": entities_by_label,
        "params_rows": params_rows,
        "module_rows": module_rows,
        "nested_fn_rows": nested_fn_rows,
        "class_fn_rows": class_fn_rows,
        "module_inclusion_rows": module_inclusion_rows,
        "js_import_rows": js_import_rows,
        "generic_import_rows": generic_import_rows,
    }


def flush_write_batches(
    tx: Any,
    batches: dict[str, Any],
) -> None:
    """Flush all accumulated write batches through UNWIND queries.

    Args:
        tx: Neo4j transaction.
        batches: Dict as returned by ``collect_file_write_data`` (with
                 ``entities_by_label`` potentially being a merged accumulation
                 across multiple files).
    """
    for label, rows in batches["entities_by_label"].items():
        run_entity_unwind(tx, label, rows)

    run_parameter_unwind(tx, batches["params_rows"])
    run_module_unwind(tx, batches["module_rows"])
    run_nested_function_unwind(tx, batches["nested_fn_rows"])
    run_class_function_unwind(tx, batches["class_fn_rows"])
    run_module_inclusion_unwind(tx, batches["module_inclusion_rows"])
    run_js_import_unwind(tx, batches["js_import_rows"])
    run_generic_import_unwind(tx, batches["generic_import_rows"])


def merge_batches(
    accumulator: dict[str, Any],
    new_batches: dict[str, Any],
) -> None:
    """Merge ``new_batches`` in-place into ``accumulator``.

    Args:
        accumulator: Target dict (modified in-place).
        new_batches: Source dict produced by ``collect_file_write_data``.
    """
    for label, rows in new_batches["entities_by_label"].items():
        accumulator["entities_by_label"].setdefault(label, []).extend(rows)
    accumulator["params_rows"].extend(new_batches["params_rows"])
    accumulator["module_rows"].extend(new_batches["module_rows"])
    accumulator["nested_fn_rows"].extend(new_batches["nested_fn_rows"])
    accumulator["class_fn_rows"].extend(new_batches["class_fn_rows"])
    accumulator["module_inclusion_rows"].extend(new_batches["module_inclusion_rows"])
    accumulator["js_import_rows"].extend(new_batches["js_import_rows"])
    accumulator["generic_import_rows"].extend(new_batches["generic_import_rows"])


def empty_accumulator() -> dict[str, Any]:
    """Return an empty write-batch accumulator."""
    return {
        "entities_by_label": {},
        "params_rows": [],
        "module_rows": [],
        "nested_fn_rows": [],
        "class_fn_rows": [],
        "module_inclusion_rows": [],
        "js_import_rows": [],
        "generic_import_rows": [],
    }


__all__ = [
    "ITEM_MAPPINGS_KEYS",
    "collect_file_write_data",
    "empty_accumulator",
    "entity_props_for_unwind",
    "flush_write_batches",
    "merge_batches",
    "run_class_function_unwind",
    "run_entity_unwind",
    "run_generic_import_unwind",
    "run_js_import_unwind",
    "run_module_inclusion_unwind",
    "run_module_unwind",
    "run_nested_function_unwind",
    "run_parameter_unwind",
]

"""Function-call relationship helpers for ``GraphBuilder``."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def safe_run_create(session: Any, query: str, params: dict[str, Any]) -> bool:
    """Run a relationship creation query and report whether it created a row.

    Args:
        session: Active database session.
        query: Cypher query to execute.
        params: Query parameters.

    Returns:
        ``True`` when the query reports at least one created relationship.
    """
    try:
        result = session.run(query, params)
        row = result.single()
        return row is not None and row.get("created", 0) > 0
    except Exception:
        return False


def create_function_calls(
    builder: Any,
    session: Any,
    file_data: dict[str, Any],
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    get_config_value_fn: Any,
    warning_logger_fn: Any,
) -> None:
    """Create ``CALLS`` relationships for one parsed file.

    Args:
        builder: ``GraphBuilder`` facade instance.
        session: Active database session.
        file_data: Parsed file payload.
        imports_map: Import resolution map collected during pre-scan.
        debug_log_fn: Debug logger callable.
        get_config_value_fn: Runtime config resolver.
        warning_logger_fn: Warning logger callable.
    """
    caller_file_path = str(Path(file_data["path"]).resolve())
    num_calls = len(file_data.get("function_calls", []))
    if num_calls > 0:
        debug_log_fn(
            f"Creating function calls for {caller_file_path} (Count: {num_calls})"
        )

    local_names = {f["name"] for f in file_data.get("functions", [])} | {
        c["name"] for c in file_data.get("classes", [])
    }
    local_imports = {
        imp.get("alias") or imp["name"].split(".")[-1]: imp["name"]
        for imp in file_data.get("imports", [])
    }
    skip_external = (
        get_config_value_fn("SKIP_EXTERNAL_RESOLUTION") or "false"
    ).lower() == "true"

    for call in file_data.get("function_calls", []):
        called_name = call["name"]
        if called_name in __builtins__:
            continue

        resolved_path = None
        full_call = call.get("full_name", called_name)
        base_obj = full_call.split(".")[0] if "." in full_call else None
        is_chained_call = full_call.count(".") > 1 if "." in full_call else False

        if is_chained_call and base_obj in (
            "self",
            "this",
            "super",
            "super()",
            "cls",
            "@",
        ):
            lookup_name = called_name
        else:
            lookup_name = base_obj if base_obj else called_name

        if (
            base_obj in ("self", "this", "super", "super()", "cls", "@")
            and not is_chained_call
        ):
            resolved_path = caller_file_path
        elif lookup_name in local_names:
            resolved_path = caller_file_path
        elif call.get("inferred_obj_type"):
            obj_type = call["inferred_obj_type"]
            possible_paths = imports_map.get(obj_type, [])
            if len(possible_paths) > 0:
                resolved_path = possible_paths[0]

        if not resolved_path:
            possible_paths = imports_map.get(lookup_name, [])
            if len(possible_paths) == 1:
                resolved_path = possible_paths[0]
            elif len(possible_paths) > 1 and lookup_name in local_imports:
                if direct_paths := _direct_import_paths(
                    imports_map, lookup_name, local_imports
                ):
                    resolved_path = direct_paths[0]
                else:
                    resolved_path = _match_import_path(
                        local_imports[lookup_name], possible_paths
                    )

        if not resolved_path:
            if not skip_external:
                warning_logger_fn(
                    f"Could not resolve call {called_name} (lookup: {lookup_name}) in {caller_file_path}"
                )
            is_unresolved_external = True
        else:
            is_unresolved_external = False

        if not resolved_path and called_name in local_names:
            resolved_path = caller_file_path
            is_unresolved_external = False
        elif (
            not resolved_path
            and called_name in imports_map
            and imports_map[called_name]
        ):
            resolved_path = _resolve_from_import_candidates(
                called_name, imports_map, local_imports
            )
        elif not resolved_path:
            resolved_path = caller_file_path

        if skip_external and is_unresolved_external:
            continue

        call_params = _build_call_params(
            call, caller_file_path, called_name, resolved_path
        )
        caller_context = call.get("context")
        if (
            caller_context
            and len(caller_context) == 3
            and caller_context[0] is not None
        ):
            _create_contextual_call_relationship(
                builder, session, caller_context, call_params
            )
        else:
            _create_file_level_call_relationship(builder, session, call_params)


def create_all_function_calls(
    builder: Any,
    all_file_data: list[dict[str, Any]],
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
) -> None:
    """Create ``CALLS`` relationships after all files are indexed.

    Args:
        builder: ``GraphBuilder`` facade instance.
        all_file_data: Parsed file payloads for the full indexing run.
        imports_map: Import resolution map collected during pre-scan.
        debug_log_fn: Debug logger callable.
    """
    debug_log_fn(f"_create_all_function_calls called with {len(all_file_data)} files")
    with builder.driver.session() as session:
        for index, file_data in enumerate(all_file_data):
            debug_log_fn(
                f"Processing file {index + 1}/{len(all_file_data)}: {file_data.get('path', 'unknown')}"
            )
            builder._create_function_calls(session, file_data, imports_map)


def name_from_symbol(symbol: str) -> str:
    """Extract a readable symbol name from a SCIP symbol identifier.

    Args:
        symbol: Raw SCIP symbol identifier.

    Returns:
        The trailing human-readable symbol name.
    """
    stripped = symbol.rstrip(".#")
    stripped = re.sub(r"\(\)\.?$", "", stripped)
    parts = re.split(r"[/#]", stripped)
    last = parts[-1] if parts else symbol
    return last or symbol


def _direct_import_paths(
    imports_map: dict[str, Any], lookup_name: str, local_imports: dict[str, str]
) -> list[str]:
    """Return direct import match candidates when a local alias is available."""
    full_import_name = local_imports[lookup_name]
    return imports_map.get(full_import_name, [])


def _match_import_path(full_import_name: str, possible_paths: list[str]) -> str | None:
    """Return the first path that matches the dotted import path."""
    for path in possible_paths:
        if full_import_name.replace(".", "/") in path:
            return path
    return None


def _resolve_from_import_candidates(
    called_name: str,
    imports_map: dict[str, Any],
    local_imports: dict[str, str],
) -> str | None:
    """Choose the best path candidate for an imported symbol."""
    candidates = imports_map[called_name]
    for path in candidates:
        for import_name in local_imports.values():
            if import_name.replace(".", "/") in path:
                return path
    return candidates[0] if candidates else None


def _build_call_params(
    call: dict[str, Any],
    caller_file_path: str,
    called_name: str,
    resolved_path: str,
) -> dict[str, Any]:
    """Build the common query parameters for function call relationships."""
    return {
        "caller_file_path": caller_file_path,
        "called_name": called_name,
        "called_file_path": resolved_path,
        "line_number": call["line_number"],
        "args": call.get("args", []),
        "full_call_name": call.get("full_name", called_name),
    }


def _create_contextual_call_relationship(
    builder: Any,
    session: Any,
    caller_context: tuple[Any, Any, Any],
    call_params: dict[str, Any],
) -> None:
    """Create a contextual call edge originating from a function or class."""
    caller_name, _, caller_line_number = caller_context
    contextual_params = {
        **call_params,
        "caller_name": caller_name,
        "caller_line_number": caller_line_number,
    }

    for query in _contextual_call_queries():
        if builder._safe_run_create(session, query, contextual_params):
            return

    builder._safe_run_create(
        session,
        """
        OPTIONAL MATCH (caller:Function {name: $caller_name, path: $caller_file_path})
        OPTIONAL MATCH (callerClass:Class {name: $caller_name, path: $caller_file_path})
        WITH COALESCE(caller, callerClass) as final_caller
        OPTIONAL MATCH (called:Function {name: $called_name})
        WITH final_caller, called
        WHERE final_caller IS NOT NULL AND called IS NOT NULL
        MERGE (final_caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(called)
        """,
        contextual_params,
    )


def _create_file_level_call_relationship(
    builder: Any, session: Any, call_params: dict[str, Any]
) -> None:
    """Create a file-level call edge for a call without a containing symbol."""
    for query in _file_level_call_queries():
        if builder._safe_run_create(session, query, call_params):
            return

    builder._safe_run_create(
        session,
        """
        OPTIONAL MATCH (caller:File {path: $caller_file_path})
        OPTIONAL MATCH (called:Function {name: $called_name})
        WITH caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(called)
        """,
        call_params,
    )


def _contextual_call_queries() -> tuple[str, ...]:
    """Return the ordered query attempts for contextual call resolution."""
    return (
        """
        OPTIONAL MATCH (caller:Function {name: $caller_name, path: $caller_file_path})
        OPTIONAL MATCH (called:Function {name: $called_name, path: $called_file_path})
        WITH caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(called)
        RETURN count(*) as created
        """,
        """
        OPTIONAL MATCH (caller:Function {name: $caller_name, path: $caller_file_path})
        OPTIONAL MATCH (called:Class {name: $called_name, path: $called_file_path})
        OPTIONAL MATCH (called)-[:CONTAINS]->(init:Function)
        WHERE init.name IN ["__init__", "constructor"]
        WITH caller, COALESCE(init, called) as final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(final_target)
        RETURN count(*) as created
        """,
        """
        OPTIONAL MATCH (caller:Class {name: $caller_name, path: $caller_file_path})
        OPTIONAL MATCH (called:Function {name: $called_name, path: $called_file_path})
        WITH caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(called)
        RETURN count(*) as created
        """,
        """
        OPTIONAL MATCH (caller:Class {name: $caller_name, path: $caller_file_path})
        OPTIONAL MATCH (called:Class {name: $called_name, path: $called_file_path})
        OPTIONAL MATCH (called)-[:CONTAINS]->(init:Function)
        WHERE init.name IN ["__init__", "constructor"]
        WITH caller, COALESCE(init, called) as final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(final_target)
        RETURN count(*) as created
        """,
    )


def _file_level_call_queries() -> tuple[str, ...]:
    """Return the ordered query attempts for file-level call resolution."""
    return (
        """
        OPTIONAL MATCH (caller:File {path: $caller_file_path})
        OPTIONAL MATCH (called:Function {name: $called_name, path: $called_file_path})
        WITH caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(called)
        RETURN count(*) as created
        """,
        """
        OPTIONAL MATCH (caller:File {path: $caller_file_path})
        OPTIONAL MATCH (called:Class {name: $called_name, path: $called_file_path})
        OPTIONAL MATCH (called)-[:CONTAINS]->(init:Function)
        WHERE init.name IN ["__init__", "constructor"]
        WITH caller, COALESCE(init, called) as final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: $line_number, args: $args, full_call_name: $full_call_name}]->(final_target)
        RETURN count(*) as created
        """,
    )


__all__ = [
    "create_all_function_calls",
    "create_function_calls",
    "name_from_symbol",
    "safe_run_create",
]

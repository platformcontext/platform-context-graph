"""Call-row preparation for function-call relationship resolution.

This module converts parsed file data into contextual and file-level
call rows that downstream batch writers persist as ``CALLS`` edges in
the graph.  It handles:

* Python-builtin and minified/bundled file filtering.
* Family-aware and legacy pre-filtering against known callable names.
* Import-path and local-name resolution heuristics.
* Splitting resolved calls into contextual (caller known) vs.
  file-level (caller unknown) buckets.

The heavy lifting lives here so that ``calls.py`` stays focused on
orchestrating resolution across the full file set and flushing batches
to Neo4j.
"""

from __future__ import annotations

import builtins as _py_builtins
from collections import Counter
from typing import Any

from ...observability import get_observability
from .call_prefilter import compatible_languages

_PYTHON_BUILTIN_NAMES: frozenset[str] = frozenset(dir(_py_builtins))
"""Built-in Python names that are never resolved as cross-file calls."""

_MINIFIED_SUFFIXES: tuple[str, ...] = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".chunk.js",
)
"""File-path suffixes indicating minified or bundled assets."""


def is_minified_or_bundled(file_path: str) -> bool:
    """Detect whether *file_path* points to a minified or bundled asset.

    Args:
        file_path: Absolute or relative path to check.

    Returns:
        ``True`` when the path ends with a known minified/bundled suffix
        (case-insensitive), ``False`` otherwise.
    """
    return any(file_path.lower().endswith(s) for s in _MINIFIED_SUFFIXES)


def prepare_call_rows(
    file_data: dict[str, Any],
    imports_map: dict[str, Any],
    *,
    caller_file_path: str,
    get_config_value_fn: Any,
    warning_logger_fn: Any,
    start_row_id: int,
    max_calls_per_file: int | None = None,
    known_callable_names: frozenset[str] | None = None,
    known_callable_names_by_family: dict[str, frozenset[str]] | None = None,
    unresolved_counter: Counter[str] | None = None,
    prefiltered_counter: Counter[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Resolve one file's calls into contextual and file-level batch rows.

    For each function call recorded in *file_data*, this function:

    1. Skips Python builtins and pre-filtered names.
    2. Attempts to resolve the target file path via local definitions,
       inferred object types, import maps, and fallback heuristics.
    3. Splits the resulting rows into *contextual* (caller function
       name is known) and *file-level* (caller unknown) buckets.

    Args:
        file_data: Parsed file dictionary containing ``function_calls``,
            ``functions``, ``classes``, ``imports``, ``path``, and
            ``repo_path`` keys.
        imports_map: Global mapping of symbol names to candidate file
            paths across all indexed repositories.
        caller_file_path: Resolved absolute path of the calling file.
        get_config_value_fn: Callable that retrieves a config value by
            key name (e.g. ``"SKIP_EXTERNAL_RESOLUTION"``).
        warning_logger_fn: Callable for emitting per-call warnings when
            counter-based aggregation is not active.
        start_row_id: First ``row_id`` to assign; incremented for each
            emitted row.
        max_calls_per_file: Optional cap on how many raw call records to
            inspect for this file.  When set, row preparation stops after
            this many calls so the cap bounds preparation work directly.
        known_callable_names: Legacy flat set of all callable names in
            the graph, used when *known_callable_names_by_family* is
            ``None``.
        known_callable_names_by_family: Language-family-keyed mapping
            of callable names for pre-filtering.
        unresolved_counter: Optional counter that accumulates names of
            calls that could not be resolved.
        prefiltered_counter: Optional counter that accumulates
            language-keyed counts of calls skipped by the family-aware
            pre-filter.

    Returns:
        A 3-tuple of ``(contextual_rows, file_level_rows, next_row_id)``
        where each row is a dict suitable for the batch Cypher writers.
    """
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
    repo_path = file_data.get("repo_path", "")
    contextual_rows: list[dict[str, Any]] = []
    file_level_rows: list[dict[str, Any]] = []
    next_row_id = start_row_id
    call_limit = None if max_calls_per_file is None else max(0, max_calls_per_file)
    inspected_calls = 0

    raw_calls = file_data.get("function_calls", [])
    for call in raw_calls:
        if call_limit is not None and inspected_calls >= call_limit:
            break
        inspected_calls += 1
        called_name = call["name"]
        if called_name in _PYTHON_BUILTIN_NAMES:
            continue

        # Family-aware pre-filter: skip calls whose name does not exist
        # within the caller's language family callable set.
        call_lang = call.get("lang")
        if known_callable_names_by_family is not None:
            if call_lang:
                family_names = known_callable_names_by_family.get(
                    call_lang, frozenset()
                )
                if called_name not in family_names:
                    if prefiltered_counter is not None:
                        prefiltered_counter[call_lang] += 1
                    if unresolved_counter is not None:
                        unresolved_counter[called_name] += 1
                    continue
            # When call_lang is None, fall through (don't filter).
        elif known_callable_names is not None:
            # Legacy path: flat name set without family grouping.
            if called_name not in known_callable_names:
                if unresolved_counter is not None:
                    unresolved_counter[called_name] += 1
                continue

        resolved_path = _resolve_call_target(
            call,
            called_name,
            caller_file_path,
            local_names,
            local_imports,
            imports_map,
        )

        if not resolved_path:
            is_unresolved_external = True
            if unresolved_counter is not None:
                unresolved_counter[called_name] += 1
            elif not skip_external:
                lookup_name = _lookup_name_for_call(call, called_name)
                warning_logger_fn(
                    f"Could not resolve call {called_name} "
                    f"(lookup: {lookup_name}) in {caller_file_path}"
                )
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
            call, caller_file_path, called_name, resolved_path, repo_path
        )
        call_params["row_id"] = next_row_id
        next_row_id += 1
        caller_context = call.get("context")
        if (
            caller_context
            and len(caller_context) == 3
            and caller_context[0] is not None
        ):
            contextual_rows.append(
                {
                    **call_params,
                    "caller_name": caller_context[0],
                }
            )
        else:
            file_level_rows.append(call_params)

    capped_calls = 0
    if call_limit is not None and len(raw_calls) > inspected_calls:
        capped_calls = len(raw_calls) - inspected_calls
    observability = get_observability()
    observability.record_call_prep_counts(
        component=observability.component,
        language=str(file_data.get("lang") or "unknown"),
        inspected_count=inspected_calls,
        capped_count=capped_calls,
    )

    return contextual_rows, file_level_rows, next_row_id


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _lookup_name_for_call(call: dict[str, Any], called_name: str) -> str:
    """Derive the symbol lookup name for a single call record.

    Args:
        call: The raw call dict from the parser.
        called_name: The short ``name`` field of the call.

    Returns:
        The name used to probe the import map -- either the base object
        of a dotted call or the called name itself.
    """
    full_call = call.get("full_name", called_name)
    base_obj = full_call.split(".")[0] if "." in full_call else None
    is_chained = full_call.count(".") > 1 if "." in full_call else False
    if is_chained and base_obj in (
        "self",
        "this",
        "super",
        "super()",
        "cls",
        "@",
    ):
        return called_name
    return base_obj if base_obj else called_name


_SELF_REFERENTS = ("self", "this", "super", "super()", "cls", "@")
"""Receiver tokens that indicate an intra-file call target."""


def _resolve_call_target(
    call: dict[str, Any],
    called_name: str,
    caller_file_path: str,
    local_names: set[str],
    local_imports: dict[str, str],
    imports_map: dict[str, Any],
) -> str | None:
    """Attempt to resolve a call to a concrete file path.

    Applies heuristics in priority order:

    1. Self/this/super receiver on a non-chained call -> caller file.
    2. Chained self/super call -> use the short name.
    3. Name present in local definitions -> caller file.
    4. Inferred object type available in imports map.
    5. Unique import-map match.
    6. Disambiguated via local import alias.

    Args:
        call: Raw call dict from the parser.
        called_name: Short name of the called function.
        caller_file_path: Absolute path of the calling file.
        local_names: Set of function/class names defined in the file.
        local_imports: Mapping of import aliases to full module paths
            for the calling file.
        imports_map: Global symbol-to-paths mapping.

    Returns:
        The resolved file path, or ``None`` if unresolved.
    """
    full_call = call.get("full_name", called_name)
    base_obj = full_call.split(".")[0] if "." in full_call else None
    is_chained = full_call.count(".") > 1 if "." in full_call else False

    if is_chained and base_obj in _SELF_REFERENTS:
        lookup_name = called_name
    else:
        lookup_name = base_obj if base_obj else called_name

    # 1. Direct self/this/super receiver.
    if base_obj in _SELF_REFERENTS and not is_chained:
        return caller_file_path

    # 2. Local definition match.
    if lookup_name in local_names:
        return caller_file_path

    # 3. Inferred object type.
    if call.get("inferred_obj_type"):
        obj_type = call["inferred_obj_type"]
        possible_paths = imports_map.get(obj_type, [])
        if possible_paths:
            return possible_paths[0]

    # 4. Import-map lookup.
    possible_paths = imports_map.get(lookup_name, [])
    if len(possible_paths) == 1:
        return possible_paths[0]
    if len(possible_paths) > 1 and lookup_name in local_imports:
        direct = _direct_import_paths(imports_map, lookup_name, local_imports)
        if direct:
            return direct[0]
        return _match_import_path(local_imports[lookup_name], possible_paths)

    return None


def _direct_import_paths(
    imports_map: dict[str, Any],
    lookup_name: str,
    local_imports: dict[str, str],
) -> list[str]:
    """Return direct import match candidates when a local alias exists.

    Args:
        imports_map: Global symbol-to-paths mapping.
        lookup_name: The alias or short name from the calling file.
        local_imports: The calling file's alias-to-module mapping.

    Returns:
        List of candidate file paths (may be empty).
    """
    full_import_name = local_imports[lookup_name]
    return imports_map.get(full_import_name, [])


def _match_import_path(full_import_name: str, possible_paths: list[str]) -> str | None:
    """Return the first path whose segments match the dotted import.

    Args:
        full_import_name: Dotted module path (e.g. ``"foo.bar.baz"``).
        possible_paths: Candidate absolute file paths.

    Returns:
        The first matching path, or ``None``.
    """
    for path in possible_paths:
        if full_import_name.replace(".", "/") in path:
            return path
    return None


def _resolve_from_import_candidates(
    called_name: str,
    imports_map: dict[str, Any],
    local_imports: dict[str, str],
) -> str | None:
    """Choose the best path candidate for an imported symbol.

    Prefers a candidate whose path segments align with one of the
    caller's import module paths.  Falls back to the first candidate
    if no import-path match is found.

    Args:
        called_name: The symbol name as it appears in the call.
        imports_map: Global symbol-to-paths mapping.
        local_imports: The calling file's alias-to-module mapping.

    Returns:
        The chosen file path, or ``None`` when no candidates exist.
    """
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
    repo_path: str,
) -> dict[str, Any]:
    """Build query parameters for a single function-call relationship.

    Args:
        call: Raw call dict from the parser.
        caller_file_path: Absolute path of the calling file.
        called_name: Short name of the called function.
        resolved_path: Resolved target file path.
        repo_path: Repository root path.

    Returns:
        Dict of parameters ready for the batch Cypher writers.
    """
    lang = call.get("lang")
    return {
        "caller_file_path": caller_file_path,
        "called_name": called_name,
        "called_file_path": resolved_path,
        "line_number": call["line_number"],
        "args": call.get("args", []),
        "full_call_name": call.get("full_name", called_name),
        "lang": lang,
        "compatible_langs": compatible_languages(lang),
        "repo_path": repo_path,
    }

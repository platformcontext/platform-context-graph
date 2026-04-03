"""Relationship projection helpers driven by stored Git facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Iterable

from platform_context_graph.facts.storage.models import FactRecordRow

from .files import iter_file_facts
from .repositories import iter_repository_facts


def _merge_import_maps(
    target: dict[str, list[str]],
    source: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Merge import maps while preserving insertion order per symbol."""

    for symbol, paths in source.items():
        merged_paths = target.setdefault(symbol, [])
        for path in paths:
            if path not in merged_paths:
                merged_paths.append(path)
    return target


def collect_relationship_projection_inputs(
    fact_records: Iterable[FactRecordRow],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Rebuild file-data and imports-map inputs from persisted Git facts."""

    records = list(fact_records)
    imports_map: dict[str, list[str]] = {}
    for repository_fact in iter_repository_facts(records):
        repo_imports_map = repository_fact.provenance.get("imports_map")
        if isinstance(repo_imports_map, dict):
            _merge_import_maps(imports_map, repo_imports_map)

    all_file_data: list[dict[str, Any]] = []
    for file_fact in iter_file_facts(records):
        if not file_fact.relative_path:
            continue
        parsed_file_data = file_fact.payload.get("parsed_file_data")
        if not isinstance(parsed_file_data, dict):
            continue
        file_data = dict(parsed_file_data)
        repo_path = str(file_data.get("repo_path") or Path(file_fact.checkout_path))
        file_path = str(
            file_data.get("path") or (Path(repo_path) / file_fact.relative_path)
        )
        file_data["path"] = file_path
        file_data["repo_path"] = repo_path
        file_data["is_dependency"] = bool(file_fact.payload.get("is_dependency", False))
        all_file_data.append(file_data)
    return all_file_data, imports_map


def project_git_relationship_fact_records(
    *,
    builder: Any,
    fact_records: Iterable[FactRecordRow],
    create_all_function_calls_fn: Any | None = None,
    create_all_inheritance_links_fn: Any | None = None,
    debug_log_fn: Any,
    warning_logger_fn: Any,
) -> dict[str, Any]:
    """Project call and inheritance relationships from stored Git facts."""

    if create_all_function_calls_fn is None:
        from platform_context_graph.graph.persistence.calls import (
            create_all_function_calls as create_all_function_calls_fn,
        )
    if create_all_inheritance_links_fn is None:
        from platform_context_graph.graph.persistence.inheritance import (
            create_all_inheritance_links as create_all_inheritance_links_fn,
        )

    all_file_data, imports_map = collect_relationship_projection_inputs(fact_records)
    if not all_file_data:
        return {
            "files": 0,
            "imports": 0,
            "call_metrics": {},
        }

    create_all_inheritance_links_fn(builder, all_file_data, imports_map)
    call_metrics = create_all_function_calls_fn(
        builder,
        all_file_data,
        imports_map,
        debug_log_fn=debug_log_fn,
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=warning_logger_fn,
    )
    return {
        "files": len(all_file_data),
        "imports": len(imports_map),
        "call_metrics": call_metrics,
    }


def project_relationship_facts(
    *,
    builder: Any,
    fact_records: Iterable[FactRecordRow],
    create_all_function_calls_fn: Any | None = None,
    create_all_inheritance_links_fn: Any | None = None,
    debug_log_fn: Any,
    warning_logger_fn: Any,
) -> dict[str, Any]:
    """Project call and inheritance relationships from stored Git facts."""

    return project_git_relationship_fact_records(
        builder=builder,
        fact_records=fact_records,
        create_all_function_calls_fn=create_all_function_calls_fn,
        create_all_inheritance_links_fn=create_all_inheritance_links_fn,
        debug_log_fn=debug_log_fn,
        warning_logger_fn=warning_logger_fn,
    )


__all__ = [
    "collect_relationship_projection_inputs",
    "project_relationship_facts",
    "project_git_relationship_fact_records",
]

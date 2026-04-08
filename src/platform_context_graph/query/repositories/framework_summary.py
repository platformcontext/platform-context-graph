"""Repository framework-summary helpers based on File-node semantics."""

from __future__ import annotations

from typing import Any

from .graph_counts import repository_scope
from .graph_counts import repository_scope_predicate

_SAMPLE_LIMIT = 5
_HTTP_VERB_ORDER = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


def build_repository_framework_summary(
    session: Any,
    repo: dict[str, Any],
) -> dict[str, Any] | None:
    """Return framework-aware file summaries for one repository."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)
        WHERE {repository_scope_predicate()}
          AND (
            size(coalesce(f.frameworks, [])) > 0
            OR f.react_boundary IS NOT NULL
            OR f.next_module_kind IS NOT NULL
          )
        RETURN f.relative_path as relative_path,
               f.frameworks as frameworks,
               f.react_boundary as react_boundary,
               f.react_component_exports as react_component_exports,
               f.react_hooks_used as react_hooks_used,
               f.next_module_kind as next_module_kind,
               f.next_route_verbs as next_route_verbs,
               f.next_metadata_exports as next_metadata_exports,
               f.next_route_segments as next_route_segments,
               f.next_runtime_boundary as next_runtime_boundary,
               f.next_request_response_apis as next_request_response_apis
        ORDER BY f.relative_path
        """,
        **repository_scope(repo),
    ).data()
    return summarize_repository_framework_rows(rows)


def summarize_repository_framework_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Summarize React/Next.js file facts from one repository."""

    framework_names: set[str] = set()
    react = _empty_react_summary()
    nextjs = _empty_nextjs_summary()

    for row in rows:
        normalized = _normalize_framework_row(row)
        if _has_react_evidence(normalized):
            framework_names.add("react")
            _accumulate_react_summary(react, normalized)
        if _has_nextjs_evidence(normalized):
            framework_names.add("nextjs")
            _accumulate_nextjs_summary(nextjs, normalized)

    if not framework_names:
        return None

    return {
        "frameworks": sorted(framework_names),
        "react": react if react["module_count"] else None,
        "nextjs": nextjs if nextjs["module_count"] else None,
    }


def _accumulate_react_summary(summary: dict[str, Any], row: dict[str, Any]) -> None:
    """Update React summary counters from one normalized file row."""

    summary["module_count"] += 1
    boundary = row["react_boundary"]
    if boundary == "client":
        summary["client_boundary_count"] += 1
    elif boundary == "server":
        summary["server_boundary_count"] += 1
    elif boundary == "shared":
        summary["shared_boundary_count"] += 1

    if row["react_component_exports"]:
        summary["component_module_count"] += 1
    if row["react_hooks_used"]:
        summary["hook_module_count"] += 1
    if len(summary["sample_modules"]) < _SAMPLE_LIMIT and row["relative_path"]:
        summary["sample_modules"].append(
            {
                "relative_path": row["relative_path"],
                "boundary": boundary,
                "component_exports": row["react_component_exports"],
                "hooks_used": row["react_hooks_used"],
            }
        )


def _accumulate_nextjs_summary(summary: dict[str, Any], row: dict[str, Any]) -> None:
    """Update Next.js summary counters from one normalized file row."""

    summary["module_count"] += 1
    module_kind = row["next_module_kind"]
    if module_kind == "page":
        summary["page_count"] += 1
    elif module_kind == "layout":
        summary["layout_count"] += 1
    elif module_kind == "route":
        summary["route_count"] += 1

    if row["next_metadata_exports"] and row["next_metadata_exports"] != "none":
        summary["metadata_module_count"] += 1
    if row["next_route_verbs"]:
        summary["route_handler_module_count"] += 1
    runtime_boundary = row["next_runtime_boundary"]
    if runtime_boundary == "client":
        summary["client_runtime_count"] += 1
    elif runtime_boundary == "server":
        summary["server_runtime_count"] += 1

    for verb in row["next_route_verbs"]:
        if verb not in summary["route_verbs"]:
            summary["route_verbs"].append(verb)

    if len(summary["sample_modules"]) < _SAMPLE_LIMIT and row["relative_path"]:
        summary["sample_modules"].append(
            {
                "relative_path": row["relative_path"],
                "module_kind": module_kind,
                "route_verbs": row["next_route_verbs"],
                "metadata_exports": row["next_metadata_exports"],
                "route_segments": row["next_route_segments"],
                "runtime_boundary": runtime_boundary,
            }
        )


def _empty_react_summary() -> dict[str, Any]:
    """Return the default React summary payload."""

    return {
        "module_count": 0,
        "client_boundary_count": 0,
        "server_boundary_count": 0,
        "shared_boundary_count": 0,
        "component_module_count": 0,
        "hook_module_count": 0,
        "sample_modules": [],
    }


def _empty_nextjs_summary() -> dict[str, Any]:
    """Return the default Next.js summary payload."""

    return {
        "module_count": 0,
        "page_count": 0,
        "layout_count": 0,
        "route_count": 0,
        "metadata_module_count": 0,
        "route_handler_module_count": 0,
        "client_runtime_count": 0,
        "server_runtime_count": 0,
        "route_verbs": [],
        "sample_modules": [],
    }


def _has_react_evidence(row: dict[str, Any]) -> bool:
    """Return whether one file row contains React evidence."""

    return bool(
        "react" in row["frameworks"]
        or row["react_boundary"]
        or row["react_component_exports"]
        or row["react_hooks_used"]
    )


def _has_nextjs_evidence(row: dict[str, Any]) -> bool:
    """Return whether one file row contains Next.js evidence."""

    return bool(
        "nextjs" in row["frameworks"]
        or row["next_module_kind"]
        or row["next_route_verbs"]
        or (row["next_metadata_exports"] and row["next_metadata_exports"] != "none")
    )


def _normalize_framework_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return one framework row with stable string/list shapes."""

    route_verbs = _normalize_string_list(row.get("next_route_verbs"))
    route_verbs.sort(
        key=lambda value: (
            _HTTP_VERB_ORDER.index(value)
            if value in _HTTP_VERB_ORDER
            else len(_HTTP_VERB_ORDER)
        )
    )
    return {
        "relative_path": str(row.get("relative_path") or "").strip(),
        "frameworks": _normalize_string_list(row.get("frameworks")),
        "react_boundary": _normalize_string(row.get("react_boundary")),
        "react_component_exports": _normalize_string_list(
            row.get("react_component_exports")
        ),
        "react_hooks_used": _normalize_string_list(row.get("react_hooks_used")),
        "next_module_kind": _normalize_string(row.get("next_module_kind")),
        "next_route_verbs": route_verbs,
        "next_metadata_exports": _normalize_metadata_exports(
            row.get("next_metadata_exports")
        ),
        "next_route_segments": _normalize_string_list(row.get("next_route_segments")),
        "next_runtime_boundary": _normalize_string(row.get("next_runtime_boundary")),
        "next_request_response_apis": _normalize_string_list(
            row.get("next_request_response_apis")
        ),
    }


def _normalize_string(value: object) -> str | None:
    """Return one non-empty string value when available."""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_string_list(value: object) -> list[str]:
    """Return a deduplicated list of non-empty strings."""

    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _normalize_metadata_exports(value: object) -> str | None:
    """Return the bounded Next.js metadata classification."""

    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str):
            normalized = first.strip()
            return normalized or None
    return None


__all__ = [
    "build_repository_framework_summary",
    "summarize_repository_framework_rows",
]

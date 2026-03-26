"""OpenAPI endpoint extraction helpers for repository content enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")


def extract_openapi_endpoints(
    database: Any,
    *,
    repo_id: str,
    relative_path: str,
    load_repo_file: Callable[..., str | None],
) -> list[dict[str, Any]]:
    """Extract endpoint paths and methods from an OpenAPI root document."""

    content = load_repo_file(database, repo_id=repo_id, relative_path=relative_path)
    if content is None:
        return []
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return []
    if not isinstance(document, dict):
        return []

    paths_node = document.get("paths")
    if not isinstance(paths_node, dict):
        return []
    if isinstance(paths_node.get("$ref"), str):
        return _extract_openapi_paths_from_ref(
            database,
            repo_id=repo_id,
            relative_path=relative_path,
            ref_value=paths_node["$ref"],
            load_repo_file=load_repo_file,
        )
    return _extract_openapi_path_items(
        database,
        repo_id=repo_id,
        document=paths_node,
        base_relative_path=relative_path,
        load_repo_file=load_repo_file,
    )


def dedupe_endpoint_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate endpoint rows while preserving order."""

    seen: set[tuple[str, tuple[str, ...], tuple[str, ...], str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("path") or ""),
            tuple(row.get("methods") or []),
            tuple(row.get("operation_ids") or []),
            str(row.get("relative_path") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _extract_openapi_paths_from_ref(
    database: Any,
    *,
    repo_id: str,
    relative_path: str,
    ref_value: str,
    load_repo_file: Callable[..., str | None],
) -> list[dict[str, Any]]:
    """Resolve one OpenAPI paths ref and extract endpoint rows from it."""

    if ref_value.startswith("#"):
        return []
    resolved_path = _resolve_relative_path(relative_path, ref_value)
    if resolved_path is None:
        return []
    content = load_repo_file(database, repo_id=repo_id, relative_path=resolved_path)
    if content is None:
        return []
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return []
    if not isinstance(document, dict):
        return []
    return _extract_openapi_path_items(
        database,
        repo_id=repo_id,
        document=document,
        base_relative_path=resolved_path,
        load_repo_file=load_repo_file,
    )


def _extract_openapi_path_items(
    database: Any,
    *,
    repo_id: str,
    document: dict[str, Any],
    base_relative_path: str,
    load_repo_file: Callable[..., str | None],
) -> list[dict[str, Any]]:
    """Extract endpoint rows from an OpenAPI paths mapping."""

    rows: list[dict[str, Any]] = []
    for api_path, item in document.items():
        if not isinstance(api_path, str) or not isinstance(item, dict):
            continue
        if isinstance(item.get("$ref"), str):
            resolved_path = _resolve_relative_path(base_relative_path, item["$ref"])
            if resolved_path is None:
                continue
            rows.extend(
                _extract_endpoint_rows_from_operation_file(
                    database,
                    repo_id=repo_id,
                    api_path=api_path,
                    relative_path=resolved_path,
                    load_repo_file=load_repo_file,
                )
            )
            continue
        rows.extend(
            _endpoint_rows_from_operation_document(
                api_path=api_path,
                operation_document=item,
                relative_path=base_relative_path,
            )
        )
    return rows


def _extract_endpoint_rows_from_operation_file(
    database: Any,
    *,
    repo_id: str,
    api_path: str,
    relative_path: str,
    load_repo_file: Callable[..., str | None],
) -> list[dict[str, Any]]:
    """Extract endpoint rows from one operation file."""

    content = load_repo_file(database, repo_id=repo_id, relative_path=relative_path)
    if content is None:
        return []
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return []
    if not isinstance(document, dict):
        return []
    return _endpoint_rows_from_operation_document(
        api_path=api_path,
        operation_document=document,
        relative_path=relative_path,
    )


def _endpoint_rows_from_operation_document(
    *,
    api_path: str,
    operation_document: dict[str, Any],
    relative_path: str,
) -> list[dict[str, Any]]:
    """Extract one normalized endpoint row from an operation document."""

    methods = [
        method for method in _HTTP_METHODS if isinstance(operation_document.get(method), dict)
    ]
    operation_ids = [
        str(operation_document[method]["operationId"])
        for method in _HTTP_METHODS
        if isinstance(operation_document.get(method), dict)
        and isinstance(operation_document[method].get("operationId"), str)
    ]
    if not methods:
        return []
    return [
        {
            "path": api_path,
            "methods": methods,
            "operation_ids": operation_ids,
            "relative_path": relative_path,
        }
    ]


def _resolve_relative_path(base_relative_path: str, ref_value: str) -> str | None:
    """Resolve one repo-relative OpenAPI ref target."""

    ref_path = ref_value.split("#", 1)[0]
    if not ref_path:
        return None
    base_path = Path(base_relative_path).parent
    return str((base_path / ref_path).as_posix())

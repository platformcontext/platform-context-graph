"""Helpers for extracting runtime service dependencies from source files."""

from __future__ import annotations

import re

_SERVICES_ARRAY_RE = re.compile(r"services\s*:\s*\[(?P<body>.*?)\]", re.DOTALL)
_STRING_LITERAL_RE = re.compile(r"""(?P<quote>['"`])(?P<value>.*?)(?P=quote)""")
_SERVICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _normalize_dependency_name(value: str, *, workload_name: str) -> str | None:
    """Normalize one declared service string into a canonical workload name."""
    candidate = value.strip()
    if not candidate or "${" in candidate:
        return None
    if candidate.startswith("/api/"):
        candidate = candidate[len("/api/") :]
    if candidate == workload_name:
        return None
    if "/" in candidate:
        return None
    if candidate in {"aws", "elastic", "elasticache"}:
        return None
    if not _SERVICE_NAME_RE.match(candidate):
        return None
    return candidate


def extract_runtime_service_dependencies(
    source: str,
    *,
    workload_name: str,
) -> list[str]:
    """Extract workload-style service dependencies from a runtime config block."""
    matches: list[str] = []
    seen: set[str] = set()
    for services_match in _SERVICES_ARRAY_RE.finditer(source):
        body = services_match.group("body")
        for token_match in _STRING_LITERAL_RE.finditer(body):
            dependency_name = _normalize_dependency_name(
                token_match.group("value"),
                workload_name=workload_name,
            )
            if dependency_name is None or dependency_name in seen:
                continue
            seen.add(dependency_name)
            matches.append(dependency_name)
    return matches


__all__ = ["extract_runtime_service_dependencies"]

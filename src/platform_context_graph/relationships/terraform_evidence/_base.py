"""Shared types and helpers for Terraform evidence extraction.

Each provider module registers resource extractors via the standard interface
defined here.  The orchestrator discovers and invokes all registered extractors
to produce relationship evidence from Terraform file content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from ..file_evidence_support import (
    CatalogEntry,
    append_evidence_for_candidate,
    append_relationship_evidence,
    match_catalog,
)
from ..models import RelationshipEvidenceFact, RepositoryCheckout

# Standard regex patterns shared across providers.
RESOURCE_BLOCK_RE = re.compile(
    r'resource\s+"(?P<resource_type>[^"]+)"\s+"(?P<resource_name>[^"]+)"\s*\{'
    r"(?P<body>.*?)\n\}",
    re.IGNORECASE | re.DOTALL,
)
MODULE_BLOCK_RE = re.compile(
    r'module\s+"(?P<module_name>[^"]+)"\s*\{(?P<body>.*?)\n\}',
    re.IGNORECASE | re.DOTALL,
)
LOCALS_BLOCK_RE = re.compile(r"locals\s*\{(?P<body>.*?)\n\}", re.IGNORECASE | re.DOTALL)
QUOTED_VALUE_RE = re.compile(r'\b(?P<key>[A-Za-z0-9_]+)\b\s*=\s*"(?P<value>[^"]+)"')
ASSIGNMENT_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z0-9_]+)\s*=\s*(?P<value>[^#\n]+)",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class ResourceRelationship:
    """One extracted relationship from a Terraform resource block.

    Provider modules yield these from their extraction functions.  The
    orchestrator translates them into ``RelationshipEvidenceFact`` objects.
    """

    evidence_kind: str
    relationship_type: str
    confidence: float
    rationale: str
    source_repo_id: str | None = None
    target_repo_id: str | None = None
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    candidate_name: str | None = None
    extra_details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractionContext:
    """Shared context passed to every resource extractor."""

    checkout: RepositoryCheckout
    catalog: Sequence[CatalogEntry]
    content: str
    file_path: Path
    local_values: dict[str, str]


# Type for resource extractor functions.
# Each takes the ExtractionContext plus regex match groups and returns evidence.
ResourceExtractorFn = Callable[
    [ExtractionContext, str, str, str],
    list[ResourceRelationship],
]


# Global registry of resource type → extractor function.
_RESOURCE_EXTRACTORS: dict[str, list[ResourceExtractorFn]] = {}


def register_resource_extractor(
    resource_types: Sequence[str],
    extractor: ResourceExtractorFn,
) -> None:
    """Register an extractor function for one or more Terraform resource types.

    Args:
        resource_types: Terraform resource type strings to match.
        extractor: Function that extracts relationships from matched blocks.
    """

    for resource_type in resource_types:
        normalized = resource_type.strip().lower()
        if normalized not in _RESOURCE_EXTRACTORS:
            _RESOURCE_EXTRACTORS[normalized] = []
        _RESOURCE_EXTRACTORS[normalized].append(extractor)


def get_registered_resource_types() -> set[str]:
    """Return all resource types with registered extractors."""

    return set(_RESOURCE_EXTRACTORS.keys())


def get_extractors_for_type(resource_type: str) -> list[ResourceExtractorFn]:
    """Return registered extractors for one resource type."""

    return _RESOURCE_EXTRACTORS.get(resource_type.strip().lower(), [])


# --- Shared parsing helpers ---


def first_quoted_value(content: str, key: str) -> str | None:
    """Extract one quoted Terraform assignment value by key."""

    for match in QUOTED_VALUE_RE.finditer(content):
        if match.group("key").lower() != key.lower():
            continue
        value = match.group("value").strip()
        if value:
            return value
    return None


def first_non_empty(*values: str | None) -> str | None:
    """Return the first non-empty string from the provided values."""

    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_assignment_value(
    content: str,
    *,
    key: str,
    local_values: dict[str, str],
    references: dict[str, str] | None = None,
) -> str | None:
    """Resolve one Terraform assignment value from quoted, local, or reference forms."""

    for match in ASSIGNMENT_RE.finditer(content):
        if match.group("key").strip().lower() != key.lower():
            continue
        resolved = _resolve_expression(
            match.group("value"),
            local_values=local_values,
            references=references or {},
        )
        if resolved:
            return resolved
    return None


def extract_local_string_values(content: str) -> dict[str, str]:
    """Extract simple quoted local assignments for Terraform expression resolution."""

    values: dict[str, str] = {}
    for block in LOCALS_BLOCK_RE.finditer(content):
        for match in ASSIGNMENT_RE.finditer(block.group("body")):
            value = _parse_quoted_literal(match.group("value"))
            if value is None:
                continue
            values[match.group("key").strip()] = value
    return values


def _resolve_expression(
    expression: str,
    *,
    local_values: dict[str, str],
    references: dict[str, str],
) -> str | None:
    """Resolve a small Terraform expression into a stable string when safe."""

    cleaned = expression.strip().rstrip(",")
    quoted = _parse_quoted_literal(cleaned)
    if quoted:
        return quoted
    if cleaned.startswith("local."):
        return local_values.get(cleaned.split(".", 1)[1].strip())
    if cleaned in references:
        return references[cleaned]
    return None


def _parse_quoted_literal(value: str) -> str | None:
    """Return the contents of one quoted string literal when present."""

    candidate = value.strip().rstrip(",")
    if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
        return candidate[1:-1].strip() or None
    return None


__all__ = [
    "ASSIGNMENT_RE",
    "ExtractionContext",
    "LOCALS_BLOCK_RE",
    "MODULE_BLOCK_RE",
    "QUOTED_VALUE_RE",
    "RESOURCE_BLOCK_RE",
    "ResourceExtractorFn",
    "ResourceRelationship",
    "extract_local_string_values",
    "first_non_empty",
    "first_quoted_value",
    "get_extractors_for_type",
    "get_registered_resource_types",
    "register_resource_extractor",
    "resolve_assignment_value",
]

"""Identity helpers for content-bearing entities."""

from __future__ import annotations

import hashlib
import re

__all__ = [
    "canonical_content_entity_id",
    "is_content_entity_id",
]

_CONTENT_ENTITY_ID_RE = re.compile(r"^content-entity:e_[0-9a-f]{12}$")


def canonical_content_entity_id(
    *,
    repo_id: str,
    relative_path: str,
    entity_type: str,
    entity_name: str,
    line_number: int,
) -> str:
    """Build the canonical identifier for a content-bearing graph entity.

    Args:
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative file path.
        entity_type: Graph label or normalized entity type.
        entity_name: Human-readable entity name.
        line_number: Starting line number for the entity.

    Returns:
        Stable content entity identifier.
    """

    identity = (
        f"{repo_id}\n{relative_path}\n{entity_type.lower()}\n"
        f"{entity_name}\n{line_number}"
    )
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    return f"content-entity:e_{digest}"


def is_content_entity_id(value: str) -> bool:
    """Return whether a string matches the content-entity identifier format.

    Args:
        value: Candidate identifier.

    Returns:
        ``True`` when the identifier matches the canonical content-entity format.
    """

    return _CONTENT_ENTITY_ID_RE.match(value) is not None

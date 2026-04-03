"""Internal models used by the content store and fallback providers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

__all__ = [
    "ContentEntityEntry",
    "ContentFileEntry",
]


def _strip_nul_bytes(value: str) -> str:
    """Return content-store text with PostgreSQL-incompatible NUL bytes removed."""

    return value.replace("\x00", "")


@dataclass(frozen=True, slots=True)
class ContentFileEntry:
    """Canonical stored content for one repository file."""

    repo_id: str
    relative_path: str
    content: str
    language: str | None = None
    artifact_type: str | None = None
    template_dialect: str | None = None
    iac_relevant: bool = False
    commit_sha: str | None = None
    indexed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def __post_init__(self) -> None:
        """Normalize stored file content for PostgreSQL text columns."""

        if "\x00" in self.content:
            object.__setattr__(self, "content", _strip_nul_bytes(self.content))

    @property
    def content_hash(self) -> str:
        """Return a stable hash for the stored file content."""

        return hashlib.sha1(self.content.encode("utf-8")).hexdigest()

    @property
    def line_count(self) -> int:
        """Return the number of logical lines in the stored file."""

        if not self.content:
            return 0
        return len(self.content.splitlines())


@dataclass(frozen=True, slots=True)
class ContentEntityEntry:
    """Canonical stored content for one parsed entity."""

    entity_id: str
    repo_id: str
    relative_path: str
    entity_type: str
    entity_name: str
    start_line: int
    end_line: int
    source_cache: str
    language: str | None = None
    artifact_type: str | None = None
    template_dialect: str | None = None
    iac_relevant: bool = False
    start_byte: int | None = None
    end_byte: int | None = None
    indexed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def __post_init__(self) -> None:
        """Normalize cached entity snippets for PostgreSQL text columns."""

        if "\x00" in self.source_cache:
            object.__setattr__(
                self,
                "source_cache",
                _strip_nul_bytes(self.source_cache),
            )

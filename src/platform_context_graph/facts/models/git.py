"""Git-specific observed fact models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import FactProvenance
from .base import stable_fact_id


@dataclass(frozen=True, slots=True)
class RepositoryObservedFact:
    """One observed repository participating in a Git indexing run."""

    repository_id: str
    checkout_path: str
    is_dependency: bool
    provenance: FactProvenance
    fact_type: str = field(init=False, default="RepositoryObserved")
    fact_id: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute a deterministic id from the repository observation."""

        object.__setattr__(
            self,
            "fact_id",
            stable_fact_id(
                fact_type=self.fact_type,
                identity={
                    "repository_id": self.repository_id,
                    "checkout_path": self.checkout_path,
                    "is_dependency": self.is_dependency,
                    "source_run_id": self.provenance.source_run_id,
                    "source_snapshot_id": self.provenance.source_snapshot_id,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class FileObservedFact:
    """One observed repository file selected for parsing."""

    repository_id: str
    checkout_path: str
    relative_path: str
    language: str | None
    is_dependency: bool
    provenance: FactProvenance
    fact_type: str = field(init=False, default="FileObserved")
    fact_id: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute a deterministic id from the file observation."""

        object.__setattr__(
            self,
            "fact_id",
            stable_fact_id(
                fact_type=self.fact_type,
                identity={
                    "repository_id": self.repository_id,
                    "relative_path": self.relative_path,
                    "language": self.language,
                    "is_dependency": self.is_dependency,
                    "source_run_id": self.provenance.source_run_id,
                    "source_snapshot_id": self.provenance.source_snapshot_id,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class ParsedEntityObservedFact:
    """One parsed entity observed in a Git-managed file."""

    repository_id: str
    checkout_path: str
    relative_path: str
    entity_kind: str
    entity_name: str
    start_line: int
    end_line: int
    language: str | None
    provenance: FactProvenance
    fact_type: str = field(init=False, default="ParsedEntityObserved")
    fact_id: str = field(init=False)

    def __post_init__(self) -> None:
        """Compute a deterministic id from the parsed entity observation."""

        object.__setattr__(
            self,
            "fact_id",
            stable_fact_id(
                fact_type=self.fact_type,
                identity={
                    "repository_id": self.repository_id,
                    "relative_path": self.relative_path,
                    "entity_kind": self.entity_kind,
                    "entity_name": self.entity_name,
                    "start_line": self.start_line,
                    "end_line": self.end_line,
                    "language": self.language,
                    "source_run_id": self.provenance.source_run_id,
                    "source_snapshot_id": self.provenance.source_snapshot_id,
                },
            ),
        )

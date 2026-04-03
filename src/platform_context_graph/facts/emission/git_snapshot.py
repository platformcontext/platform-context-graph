"""Emit typed facts from Git repository parse snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.models.base import FactProvenance
from platform_context_graph.facts.models.base import stable_fact_id
from platform_context_graph.facts.models.git import FileObservedFact
from platform_context_graph.facts.models.git import ParsedEntityObservedFact
from platform_context_graph.facts.models.git import RepositoryObservedFact
from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.storage.models import FactRunRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow


@dataclass(frozen=True, slots=True)
class GitSnapshotFactEmissionResult:
    """Outcome metadata for one emitted repository snapshot batch."""

    repository_id: str
    source_run_id: str
    source_snapshot_id: str
    work_item_id: str
    fact_count: int
    work_item: FactWorkItemRow | None = None


def build_git_snapshot_id(
    *,
    repository_id: str,
    checkout_path: str,
    source_run_id: str,
) -> str:
    """Return the deterministic snapshot identifier for one Git repo emission."""

    return stable_fact_id(
        fact_type="GitSnapshot",
        identity={
            "repository_id": repository_id,
            "checkout_path": checkout_path,
            "source_run_id": source_run_id,
        },
    )


def build_git_projection_work_item_id(
    *,
    repository_id: str,
    source_run_id: str,
    source_snapshot_id: str,
) -> str:
    """Return the deterministic work-item identifier for one Git snapshot."""

    return stable_fact_id(
        fact_type="FactProjectionWorkItem",
        identity={
            "repository_id": repository_id,
            "source_run_id": source_run_id,
            "source_snapshot_id": source_snapshot_id,
        },
    )


def _fact_record_from_repository_fact(
    fact: RepositoryObservedFact,
) -> FactRecordRow:
    """Return the storage row for one repository observation."""

    return FactRecordRow(
        fact_id=fact.fact_id,
        fact_type=fact.fact_type,
        repository_id=fact.repository_id,
        checkout_path=fact.checkout_path,
        relative_path=None,
        source_system=fact.provenance.source_system,
        source_run_id=fact.provenance.source_run_id,
        source_snapshot_id=fact.provenance.source_snapshot_id,
        payload={"is_dependency": fact.is_dependency},
        observed_at=fact.provenance.observed_at,
        ingested_at=fact.provenance.ingested_at,
        provenance=fact.provenance.details,
    )


def _fact_record_from_file_fact(fact: FileObservedFact) -> FactRecordRow:
    """Return the storage row for one file observation."""

    return FactRecordRow(
        fact_id=fact.fact_id,
        fact_type=fact.fact_type,
        repository_id=fact.repository_id,
        checkout_path=fact.checkout_path,
        relative_path=fact.relative_path,
        source_system=fact.provenance.source_system,
        source_run_id=fact.provenance.source_run_id,
        source_snapshot_id=fact.provenance.source_snapshot_id,
        payload={
            "language": fact.language,
            "is_dependency": fact.is_dependency,
        },
        observed_at=fact.provenance.observed_at,
        ingested_at=fact.provenance.ingested_at,
        provenance=fact.provenance.details,
    )


def _sanitize_for_json(value: Any) -> Any:
    """Recursively convert Path objects to strings for JSON serialization."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_sanitize_for_json(item) for item in value)
    return value


def _file_fact_payload_from_snapshot_entry(
    *,
    entry: dict[str, Any],
    is_dependency: bool,
) -> dict[str, Any]:
    """Return the persisted file-fact payload for one parsed snapshot entry."""

    parsed_file_data = {
        key: _sanitize_for_json(value)
        for key, value in entry.items()
        if key not in {"path", "repo_path", "is_dependency"}
    }
    return {
        "language": entry.get("lang"),
        "is_dependency": is_dependency,
        "parsed_file_data": parsed_file_data,
    }


def _fact_record_from_entity_fact(
    fact: ParsedEntityObservedFact,
) -> FactRecordRow:
    """Return the storage row for one parsed entity observation."""

    return FactRecordRow(
        fact_id=fact.fact_id,
        fact_type=fact.fact_type,
        repository_id=fact.repository_id,
        checkout_path=fact.checkout_path,
        relative_path=fact.relative_path,
        source_system=fact.provenance.source_system,
        source_run_id=fact.provenance.source_run_id,
        source_snapshot_id=fact.provenance.source_snapshot_id,
        payload={
            "entity_kind": fact.entity_kind,
            "entity_name": fact.entity_name,
            "start_line": fact.start_line,
            "end_line": fact.end_line,
            "language": fact.language,
        },
        observed_at=fact.provenance.observed_at,
        ingested_at=fact.provenance.ingested_at,
        provenance=fact.provenance.details,
    )


def _iter_entity_facts(
    *,
    repository_id: str,
    checkout_path: str,
    provenance: FactProvenance,
    file_data: list[dict[str, Any]],
) -> list[ParsedEntityObservedFact]:
    """Return parsed entity facts derived from snapshot file data."""

    entity_facts: list[ParsedEntityObservedFact] = []
    for entry in file_data:
        relative_path = str(Path(entry["path"]).resolve().relative_to(checkout_path))
        language = entry.get("lang")
        for field_name, entity_kind in (
            ("functions", "Function"),
            ("classes", "Class"),
            ("variables", "Variable"),
        ):
            for entity in entry.get(field_name, []):
                entity_facts.append(
                    ParsedEntityObservedFact(
                        repository_id=repository_id,
                        checkout_path=checkout_path,
                        relative_path=relative_path,
                        entity_kind=entity_kind,
                        entity_name=str(entity.get("name") or ""),
                        start_line=int(entity.get("line_number") or 0),
                        end_line=int(
                            entity.get("end_line") or entity.get("line_number") or 0
                        ),
                        language=language,
                        provenance=provenance,
                    )
                )
    return entity_facts


def emit_git_snapshot_facts(
    *,
    snapshot: RepositoryParseSnapshot,
    repository_id: str,
    source_run_id: str,
    source_snapshot_id: str,
    is_dependency: bool,
    fact_store: Any,
    work_queue: Any,
    observed_at: Any,
    inline_projection_owner: str | None = None,
    inline_projection_lease_ttl_seconds: int = 300,
) -> GitSnapshotFactEmissionResult:
    """Persist fact rows and enqueue one projection work item for a snapshot."""

    checkout_path = str(Path(snapshot.repo_path).resolve())
    provenance = FactProvenance(
        source_system="git",
        source_run_id=source_run_id,
        source_snapshot_id=source_snapshot_id,
        observed_at=observed_at,
        details={"imports_map": snapshot.imports_map},
    )
    repository_fact = RepositoryObservedFact(
        repository_id=repository_id,
        checkout_path=checkout_path,
        is_dependency=is_dependency,
        provenance=provenance,
    )
    file_fact_rows: list[FactRecordRow] = []
    file_facts = []
    for entry in snapshot.file_data:
        file_fact = FileObservedFact(
            repository_id=repository_id,
            checkout_path=checkout_path,
            relative_path=str(Path(entry["path"]).resolve().relative_to(checkout_path)),
            language=entry.get("lang"),
            is_dependency=is_dependency,
            provenance=provenance,
        )
        file_facts.append(file_fact)
        file_fact_row = _fact_record_from_file_fact(file_fact)
        file_fact_rows.append(
            FactRecordRow(
                fact_id=file_fact_row.fact_id,
                fact_type=file_fact_row.fact_type,
                repository_id=file_fact_row.repository_id,
                checkout_path=file_fact_row.checkout_path,
                relative_path=file_fact_row.relative_path,
                source_system=file_fact_row.source_system,
                source_run_id=file_fact_row.source_run_id,
                source_snapshot_id=file_fact_row.source_snapshot_id,
                payload=_file_fact_payload_from_snapshot_entry(
                    entry=entry,
                    is_dependency=is_dependency,
                ),
                observed_at=file_fact_row.observed_at,
                ingested_at=file_fact_row.ingested_at,
                provenance=file_fact_row.provenance,
            )
        )
    entity_facts = _iter_entity_facts(
        repository_id=repository_id,
        checkout_path=checkout_path,
        provenance=provenance,
        file_data=snapshot.file_data,
    )

    fact_store.upsert_fact_run(
        FactRunRow(
            source_run_id=source_run_id,
            source_system="git",
            source_snapshot_id=source_snapshot_id,
            repository_id=repository_id,
            status="pending",
            started_at=observed_at,
        )
    )
    fact_store.upsert_facts(
        [
            _fact_record_from_repository_fact(repository_fact),
            *file_fact_rows,
            *[_fact_record_from_entity_fact(fact) for fact in entity_facts],
        ]
    )
    work_item_id = build_git_projection_work_item_id(
        repository_id=repository_id,
        source_run_id=source_run_id,
        source_snapshot_id=source_snapshot_id,
    )
    initial_work_item = FactWorkItemRow(
        work_item_id=work_item_id,
        work_type="project-git-facts",
        repository_id=repository_id,
        source_run_id=source_run_id,
        lease_owner=inline_projection_owner,
        lease_expires_at=(
            observed_at + timedelta(seconds=inline_projection_lease_ttl_seconds)
            if inline_projection_owner is not None
            else None
        ),
        status="leased" if inline_projection_owner is not None else "pending",
        attempt_count=1 if inline_projection_owner is not None else 0,
        last_attempt_started_at=observed_at if inline_projection_owner is not None else None,
        created_at=observed_at,
        updated_at=observed_at,
    )
    work_queue.enqueue_work_item(initial_work_item)
    return GitSnapshotFactEmissionResult(
        repository_id=repository_id,
        source_run_id=source_run_id,
        source_snapshot_id=source_snapshot_id,
        work_item_id=work_item_id,
        fact_count=1 + len(file_facts) + len(entity_facts),
        work_item=initial_work_item,
    )

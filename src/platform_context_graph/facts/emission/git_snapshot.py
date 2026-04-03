"""Emit typed facts from Git repository parse snapshots."""

from __future__ import annotations

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
) -> int:
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
    file_facts = [
        FileObservedFact(
            repository_id=repository_id,
            checkout_path=checkout_path,
            relative_path=str(Path(entry["path"]).resolve().relative_to(checkout_path)),
            language=entry.get("lang"),
            is_dependency=is_dependency,
            provenance=provenance,
        )
        for entry in snapshot.file_data
    ]
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
            *[_fact_record_from_file_fact(fact) for fact in file_facts],
            *[_fact_record_from_entity_fact(fact) for fact in entity_facts],
        ]
    )
    work_queue.enqueue_work_item(
        FactWorkItemRow(
            work_item_id=stable_fact_id(
                fact_type="FactProjectionWorkItem",
                identity={
                    "repository_id": repository_id,
                    "source_run_id": source_run_id,
                    "source_snapshot_id": source_snapshot_id,
                },
            ),
            work_type="project-git-facts",
            repository_id=repository_id,
            source_run_id=source_run_id,
            status="pending",
        )
    )
    return 1 + len(file_facts) + len(entity_facts)

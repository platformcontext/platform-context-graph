"""Helpers for recording projection decisions from resolution stages."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL
from uuid import uuid5

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow

from .models import ProjectionDecisionEvidenceRow
from .models import ProjectionDecisionRow

_DECISION_EVIDENCE_LIMIT = 20


def _decision_confidence(stage: str) -> tuple[float, str]:
    """Return a bounded confidence score and rationale for one stage."""

    if stage in {"project_workloads", "project_platforms"}:
        return (
            0.9,
            "Projected from persisted repository facts and materialized repository paths",
        )
    if stage == "project_relationships":
        return (
            0.75,
            "Projected from parsed file facts and repository import metadata",
        )
    return (
        0.6,
        "Projected from persisted fact inputs without a specialized confidence rule",
    )


def build_projection_decision(
    *,
    stage: str,
    work_item: FactWorkItemRow,
    fact_records: list[FactRecordRow],
    output_count: int,
    created_at: datetime,
) -> ProjectionDecisionRow:
    """Build one persisted projection decision for a resolution stage."""

    confidence_score, confidence_reason = _decision_confidence(stage)
    return ProjectionDecisionRow(
        decision_id=str(
            uuid5(
                NAMESPACE_URL,
                f"{work_item.work_item_id}:{stage}:{work_item.source_run_id}",
            )
        ),
        decision_type=stage,
        repository_id=work_item.repository_id,
        source_run_id=work_item.source_run_id,
        work_item_id=work_item.work_item_id,
        subject=work_item.repository_id,
        confidence_score=confidence_score,
        confidence_reason=confidence_reason,
        provenance_summary={
            "fact_count": len(fact_records),
            "output_count": output_count,
            "sample_fact_ids": [fact.fact_id for fact in fact_records[:10]],
        },
        created_at=created_at,
    )


def build_projection_evidence(
    *,
    decision: ProjectionDecisionRow,
    fact_records: list[FactRecordRow],
    created_at: datetime,
) -> list[ProjectionDecisionEvidenceRow]:
    """Build bounded evidence rows for one projection decision."""

    evidence_rows: list[ProjectionDecisionEvidenceRow] = []
    for fact in fact_records[:_DECISION_EVIDENCE_LIMIT]:
        evidence_rows.append(
            ProjectionDecisionEvidenceRow(
                evidence_id=str(uuid5(NAMESPACE_URL, f"{decision.decision_id}:{fact.fact_id}")),
                decision_id=decision.decision_id,
                fact_id=fact.fact_id,
                evidence_kind="input",
                detail={"fact_type": fact.fact_type, "relative_path": fact.relative_path},
                created_at=created_at,
            )
        )
    return evidence_rows

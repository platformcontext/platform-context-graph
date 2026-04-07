"""Public investigation query entrypoints."""

from __future__ import annotations

import time
from typing import Any

from ..observability import get_observability
from ..observability import trace_query
from ..observability.investigation_metrics import (
    build_investigation_span_attributes,
    record_investigation_metrics,
)
from .investigation_intent import (
    infer_investigation_intent,
    normalize_investigation_intent,
)
from .investigation_service import investigate_service as investigate_service_query

__all__ = ["investigate_service"]


def investigate_service(
    database: Any,
    *,
    service_name: str,
    environment: str | None = None,
    intent: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Return an orchestrated investigation for one service."""

    resolved_intent = normalize_investigation_intent(intent)
    if resolved_intent == "overview" and question:
        resolved_intent = infer_investigation_intent(question)

    start_time = time.perf_counter()
    with trace_query(
        "investigate_service",
        attributes={
            "pcg.investigation.service_name": service_name,
            "pcg.investigation.intent": resolved_intent,
            "pcg.investigation.environment": environment or "unknown",
        },
    ) as span:
        try:
            response = investigate_service_query(
                database,
                service_name=service_name,
                environment=environment,
                intent=resolved_intent,
                question=question,
            )
            _record_investigation_observability(
                span=span,
                service_name=service_name,
                environment=environment,
                intent=resolved_intent,
                response=response,
                duration_seconds=max(time.perf_counter() - start_time, 0.0),
                outcome="success",
            )
            return response
        except Exception:
            _record_investigation_observability(
                span=span,
                service_name=service_name,
                environment=environment,
                intent=resolved_intent,
                response=None,
                duration_seconds=max(time.perf_counter() - start_time, 0.0),
                outcome="error",
            )
            raise


def _record_investigation_observability(
    *,
    span: Any,
    service_name: str,
    environment: str | None,
    intent: str,
    response: dict[str, Any] | None,
    duration_seconds: float,
    outcome: str,
) -> None:
    """Attach investigation span attributes and emit investigation metrics."""

    coverage_summary = dict((response or {}).get("coverage_summary") or {})
    evidence_families_found = list(
        (response or {}).get("evidence_families_found") or []
    )
    missing_evidence_families = list(
        coverage_summary.get("missing_evidence_families") or []
    )
    span_attributes = build_investigation_span_attributes(
        service_name=service_name,
        intent=intent,
        environment=environment,
        deployment_mode=str(coverage_summary.get("deployment_mode") or "unknown"),
        repositories_considered_count=len(
            list((response or {}).get("repositories_considered") or [])
        ),
        repositories_with_evidence_count=len(
            list((response or {}).get("repositories_with_evidence") or [])
        ),
        evidence_families_found=evidence_families_found,
        missing_evidence_families=missing_evidence_families,
        outcome=outcome,
    )
    if span is not None:
        for key, value in span_attributes.items():
            span.set_attribute(key, value)

    record_investigation_metrics(
        get_observability(),
        intent=intent,
        deployment_mode=str(coverage_summary.get("deployment_mode") or "unknown"),
        repositories_considered_count=int(
            span_attributes["pcg.investigation.repositories_considered_count"]
        ),
        repositories_with_evidence_count=int(
            span_attributes["pcg.investigation.repositories_with_evidence_count"]
        ),
        missing_evidence_families_count=len(missing_evidence_families),
        duration_seconds=duration_seconds,
        outcome=outcome,
    )

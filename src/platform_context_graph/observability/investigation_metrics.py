"""Telemetry helpers for service investigation queries."""

from __future__ import annotations

from typing import Any

_INVESTIGATION_INSTRUMENTS: dict[int, dict[str, Any]] = {}


def _get_investigation_instruments(runtime: Any) -> dict[str, Any]:
    """Create or reuse OTEL instruments for investigation telemetry."""

    if not runtime.enabled or runtime.meter is None:
        return {}

    runtime_id = id(runtime)
    cached = _INVESTIGATION_INSTRUMENTS.get(runtime_id)
    if cached is not None:
        return cached

    instruments = {
        "investigations_total": runtime.meter.create_counter(
            "pcg_investigations_total"
        ),
        "investigation_duration": runtime.meter.create_histogram(
            "pcg_investigation_duration_seconds",
            unit="s",
        ),
        "investigation_coverage_total": runtime.meter.create_counter(
            "pcg_investigation_coverage_total"
        ),
        "investigation_repositories_considered": runtime.meter.create_histogram(
            "pcg_investigation_repositories_considered",
            unit="repos",
        ),
        "investigation_repositories_with_evidence": runtime.meter.create_histogram(
            "pcg_investigation_repositories_with_evidence",
            unit="repos",
        ),
    }
    _INVESTIGATION_INSTRUMENTS[runtime_id] = instruments
    return instruments


def build_investigation_span_attributes(
    *,
    service_name: str,
    intent: str,
    environment: str | None,
    deployment_mode: str,
    repositories_considered_count: int,
    repositories_with_evidence_count: int,
    evidence_families_found: list[str],
    missing_evidence_families: list[str],
    outcome: str,
) -> dict[str, Any]:
    """Build stable span attributes for one investigation query."""

    return {
        "pcg.investigation.service_name": service_name,
        "pcg.investigation.intent": intent,
        "pcg.investigation.environment": environment or "unknown",
        "pcg.investigation.deployment_mode": deployment_mode,
        "pcg.investigation.repositories_considered_count": (
            repositories_considered_count
        ),
        "pcg.investigation.repositories_with_evidence_count": (
            repositories_with_evidence_count
        ),
        "pcg.investigation.evidence_families_found_count": len(evidence_families_found),
        "pcg.investigation.missing_evidence_families_count": len(
            missing_evidence_families
        ),
        "pcg.investigation.evidence_families_found": ",".join(evidence_families_found),
        "pcg.investigation.missing_evidence_families": ",".join(
            missing_evidence_families
        ),
        "pcg.investigation.outcome": outcome,
    }


def record_investigation_metrics(
    runtime: Any,
    *,
    intent: str,
    deployment_mode: str,
    repositories_considered_count: int,
    repositories_with_evidence_count: int,
    missing_evidence_families_count: int,
    duration_seconds: float,
    outcome: str,
) -> None:
    """Record low-cardinality metrics for one investigation query."""

    if not runtime.enabled:
        return

    instruments = _get_investigation_instruments(runtime)
    if not instruments:
        return

    attrs = {
        "pcg.component": runtime.component,
        "pcg.investigation.intent": intent,
        "pcg.investigation.deployment_mode": deployment_mode,
        "pcg.investigation.outcome": outcome,
    }
    coverage_attrs = {
        **attrs,
        "pcg.investigation.has_missing_evidence": str(
            missing_evidence_families_count > 0
        ).lower(),
    }

    instruments["investigations_total"].add(1, attrs)
    instruments["investigation_duration"].record(duration_seconds, attrs)
    instruments["investigation_coverage_total"].add(1, coverage_attrs)
    instruments["investigation_repositories_considered"].record(
        repositories_considered_count,
        attrs,
    )
    instruments["investigation_repositories_with_evidence"].record(
        repositories_with_evidence_count,
        attrs,
    )

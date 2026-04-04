"""Instrument registration for facts-first and resolution telemetry."""

from __future__ import annotations

from typing import Any

from .fact_scaling_metrics import setup_fact_scaling_instruments
from .projection_hot_path_metrics import setup_projection_hot_path_instruments


def setup_fact_resolution_instruments(runtime: Any) -> None:
    """Initialize facts and resolution instruments for one runtime."""

    if not runtime.enabled or runtime.meter is None:
        return

    runtime._fact_resolution_instruments["fact_records_total"] = (
        runtime.meter.create_counter("pcg_fact_records_total")
    )
    runtime._fact_resolution_instruments["fact_emission_duration"] = (
        runtime.meter.create_histogram("pcg_fact_emission_duration_seconds", unit="s")
    )
    runtime._fact_resolution_instruments["fact_work_items_total"] = (
        runtime.meter.create_counter("pcg_fact_work_items_total")
    )
    runtime._fact_resolution_instruments["resolution_work_items_total"] = (
        runtime.meter.create_counter("pcg_resolution_work_items_total")
    )
    runtime._fact_resolution_instruments["resolution_work_item_duration"] = (
        runtime.meter.create_histogram(
            "pcg_resolution_work_item_duration_seconds", unit="s"
        )
    )
    runtime._fact_resolution_instruments["resolution_stage_duration"] = (
        runtime.meter.create_histogram(
            "pcg_resolution_stage_duration_seconds", unit="s"
        )
    )
    runtime._fact_resolution_instruments["resolution_facts_loaded_total"] = (
        runtime.meter.create_counter("pcg_resolution_facts_loaded_total")
    )
    runtime._fact_resolution_instruments["fact_store_operations_total"] = (
        runtime.meter.create_counter("pcg_fact_store_operations_total")
    )
    runtime._fact_resolution_instruments["fact_store_operation_duration"] = (
        runtime.meter.create_histogram(
            "pcg_fact_store_operation_duration_seconds", unit="s"
        )
    )
    runtime._fact_resolution_instruments["fact_store_rows_total"] = (
        runtime.meter.create_counter("pcg_fact_store_rows_total")
    )
    runtime._fact_resolution_instruments["fact_queue_operations_total"] = (
        runtime.meter.create_counter("pcg_fact_queue_operations_total")
    )
    runtime._fact_resolution_instruments["fact_queue_operation_duration"] = (
        runtime.meter.create_histogram(
            "pcg_fact_queue_operation_duration_seconds", unit="s"
        )
    )
    runtime._fact_resolution_instruments["fact_queue_rows_total"] = (
        runtime.meter.create_counter("pcg_fact_queue_rows_total")
    )
    runtime._fact_resolution_instruments["resolution_claim_duration"] = (
        runtime.meter.create_histogram(
            "pcg_resolution_claim_duration_seconds", unit="s"
        )
    )
    runtime._fact_resolution_instruments["resolution_idle_sleep"] = (
        runtime.meter.create_histogram("pcg_resolution_idle_sleep_seconds", unit="s")
    )
    runtime._fact_resolution_instruments["resolution_stage_output_total"] = (
        runtime.meter.create_counter("pcg_resolution_stage_output_total")
    )
    runtime._fact_resolution_instruments["resolution_stage_failures_total"] = (
        runtime.meter.create_counter("pcg_resolution_stage_failures_total")
    )
    runtime._fact_resolution_instruments["resolution_failure_classifications_total"] = (
        runtime.meter.create_counter("pcg_resolution_failure_classifications_total")
    )
    runtime._fact_resolution_instruments["projection_decisions_total"] = (
        runtime.meter.create_counter("pcg_projection_decisions_total")
    )
    runtime._fact_resolution_instruments["projection_confidence_score"] = (
        runtime.meter.create_histogram("pcg_projection_confidence_score")
    )
    runtime._fact_resolution_instruments["projection_decision_evidence_total"] = (
        runtime.meter.create_counter("pcg_projection_decision_evidence_total")
    )
    runtime._fact_resolution_instruments["admin_fact_actions_total"] = (
        runtime.meter.create_counter("pcg_admin_fact_actions_total")
    )
    runtime.meter.create_observable_gauge(
        "pcg_fact_queue_depth",
        callbacks=[runtime._observe_fact_queue_depth],
    )
    runtime.meter.create_observable_gauge(
        "pcg_fact_queue_oldest_age_seconds",
        callbacks=[runtime._observe_fact_queue_oldest_age_seconds],
        unit="s",
    )
    runtime.meter.create_observable_gauge(
        "pcg_resolution_workers_active",
        callbacks=[runtime._observe_resolution_workers_active],
    )
    setup_fact_scaling_instruments(runtime)
    setup_projection_hot_path_instruments(runtime)

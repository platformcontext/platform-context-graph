"""Fact and resolution telemetry helpers for the observability runtime."""

from __future__ import annotations

import threading
from typing import Any

from .otel import Observation


class RuntimeFactResolutionMetricsMixin:
    """Provide facts-first and resolution-engine metric helpers."""

    enabled: bool
    _lock: threading.Lock
    _fact_resolution_instruments: dict[str, Any]
    _fact_queue_depth: dict[tuple[tuple[str, str], ...], int]
    _fact_queue_oldest_age_seconds: dict[tuple[tuple[str, str], ...], float]

    def record_fact_emission(
        self,
        *,
        component: str,
        source_system: str,
        work_type: str,
        fact_count: int,
        duration_seconds: float,
    ) -> None:
        """Record one fact-emission batch."""

        if not self.enabled:
            return
        fact_records_total = self._fact_resolution_instruments.get("fact_records_total")
        fact_emission_duration = self._fact_resolution_instruments.get(
            "fact_emission_duration"
        )
        attrs = {
            "pcg.component": component,
            "pcg.source_system": source_system,
            "pcg.work_type": work_type,
        }
        if fact_records_total is not None:
            fact_records_total.add(fact_count, attrs)
        if fact_emission_duration is not None:
            fact_emission_duration.record(duration_seconds, attrs)

    def record_fact_work_item(
        self,
        *,
        component: str,
        work_type: str,
        outcome: str,
    ) -> None:
        """Record one fact work-item lifecycle transition."""

        if not self.enabled:
            return
        fact_work_items_total = self._fact_resolution_instruments.get(
            "fact_work_items_total"
        )
        if fact_work_items_total is not None:
            fact_work_items_total.add(
                1,
                {
                    "pcg.component": component,
                    "pcg.work_type": work_type,
                    "pcg.outcome": outcome,
                },
            )

    def set_fact_queue_depth(
        self,
        *,
        component: str,
        work_type: str,
        status: str,
        depth: int,
    ) -> None:
        """Set the observable facts queue depth for one work type and status."""

        key = tuple(
            sorted(
                {
                    "pcg.component": component,
                    "pcg.work_type": work_type,
                    "pcg.queue_status": status,
                }.items()
            )
        )
        with self._lock:
            if depth <= 0:
                self._fact_queue_depth.pop(key, None)
            else:
                self._fact_queue_depth[key] = depth

    def set_fact_queue_oldest_age_seconds(
        self,
        *,
        component: str,
        work_type: str,
        status: str,
        age_seconds: float,
    ) -> None:
        """Set the observable age of the oldest queue item."""

        key = tuple(
            sorted(
                {
                    "pcg.component": component,
                    "pcg.work_type": work_type,
                    "pcg.queue_status": status,
                }.items()
            )
        )
        with self._lock:
            if age_seconds <= 0:
                self._fact_queue_oldest_age_seconds.pop(key, None)
            else:
                self._fact_queue_oldest_age_seconds[key] = age_seconds

    def record_resolution_work_item(
        self,
        *,
        component: str,
        work_type: str,
        outcome: str,
        duration_seconds: float | None = None,
    ) -> None:
        """Record one resolution work-item lifecycle event."""

        if not self.enabled:
            return
        work_items_total = self._fact_resolution_instruments.get(
            "resolution_work_items_total"
        )
        work_item_duration = self._fact_resolution_instruments.get(
            "resolution_work_item_duration"
        )
        attrs = {
            "pcg.component": component,
            "pcg.work_type": work_type,
            "pcg.outcome": outcome,
        }
        if work_items_total is not None:
            work_items_total.add(1, attrs)
        if duration_seconds is not None and work_item_duration is not None:
            work_item_duration.record(duration_seconds, attrs)

    def record_resolution_stage_duration(
        self,
        *,
        component: str,
        work_type: str,
        stage: str,
        duration_seconds: float,
    ) -> None:
        """Record one resolution stage duration."""

        if not self.enabled:
            return
        stage_duration = self._fact_resolution_instruments.get(
            "resolution_stage_duration"
        )
        if stage_duration is not None:
            stage_duration.record(
                duration_seconds,
                {
                    "pcg.component": component,
                    "pcg.work_type": work_type,
                    "pcg.stage": stage,
                },
            )

    def record_resolution_facts_loaded(
        self,
        *,
        component: str,
        work_type: str,
        fact_count: int,
    ) -> None:
        """Record how many facts were loaded for one work item."""

        if not self.enabled:
            return
        facts_loaded_total = self._fact_resolution_instruments.get(
            "resolution_facts_loaded_total"
        )
        if facts_loaded_total is not None:
            facts_loaded_total.add(
                fact_count,
                {
                    "pcg.component": component,
                    "pcg.work_type": work_type,
                },
            )

    def _observe_fact_queue_depth(self, _options: Any) -> list[Observation]:
        """Produce facts queue depth observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._fact_queue_depth.items())
            ]

    def _observe_fact_queue_oldest_age_seconds(
        self, _options: Any
    ) -> list[Observation]:
        """Produce oldest facts queue age observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._fact_queue_oldest_age_seconds.items())
            ]


def setup_fact_resolution_instruments(runtime: Any) -> None:
    """Initialize facts and resolution instruments for one runtime."""

    if not runtime.enabled or runtime.meter is None:
        return

    runtime._fact_resolution_instruments["fact_records_total"] = (
        runtime.meter.create_counter("pcg_fact_records_total")
    )
    runtime._fact_resolution_instruments["fact_emission_duration"] = (
        runtime.meter.create_histogram(
            "pcg_fact_emission_duration_seconds",
            unit="s",
        )
    )
    runtime._fact_resolution_instruments["fact_work_items_total"] = (
        runtime.meter.create_counter("pcg_fact_work_items_total")
    )
    runtime._fact_resolution_instruments["resolution_work_items_total"] = (
        runtime.meter.create_counter("pcg_resolution_work_items_total")
    )
    runtime._fact_resolution_instruments["resolution_work_item_duration"] = (
        runtime.meter.create_histogram(
            "pcg_resolution_work_item_duration_seconds",
            unit="s",
        )
    )
    runtime._fact_resolution_instruments["resolution_stage_duration"] = (
        runtime.meter.create_histogram(
            "pcg_resolution_stage_duration_seconds",
            unit="s",
        )
    )
    runtime._fact_resolution_instruments["resolution_facts_loaded_total"] = (
        runtime.meter.create_counter("pcg_resolution_facts_loaded_total")
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


__all__ = [
    "RuntimeFactResolutionMetricsMixin",
    "setup_fact_resolution_instruments",
]

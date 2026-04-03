"""Scaling-focused telemetry helpers for facts-first runtime services."""

from __future__ import annotations

import threading
from typing import Any

from .otel import Observation

_POOL_LOCK = threading.Lock()
_POOL_SIZE: dict[tuple[tuple[str, str], ...], int] = {}
_POOL_AVAILABLE: dict[tuple[tuple[str, str], ...], int] = {}
_POOL_WAITING: dict[tuple[tuple[str, str], ...], int] = {}


class RuntimeFactScalingMetricsMixin:
    """Provide scaling-focused helpers for fact-store and queue telemetry."""

    enabled: bool
    _fact_resolution_instruments: dict[str, Any]

    def set_fact_postgres_pool_stats(
        self,
        *,
        component: str,
        pool_name: str,
        size: int,
        available: int,
        waiting: int,
    ) -> None:
        """Set the latest connection-pool stats for fact Postgres services."""

        if not self.enabled:
            return
        set_fact_postgres_pool_stats(
            component=component,
            pool_name=pool_name,
            size=size,
            available=available,
            waiting=waiting,
        )

    def record_fact_postgres_pool_acquire(
        self,
        *,
        component: str,
        pool_name: str,
        outcome: str,
        duration_seconds: float,
    ) -> None:
        """Record one fact Postgres pool-acquire attempt."""

        if not self.enabled:
            return
        acquire_duration = self._fact_resolution_instruments.get(
            "fact_postgres_pool_acquire_duration"
        )
        if acquire_duration is not None:
            acquire_duration.record(
                duration_seconds,
                {
                    "pcg.component": component,
                    "pcg.pool": pool_name,
                    "pcg.outcome": outcome,
                },
            )

    def record_fact_queue_retry_age(
        self,
        *,
        component: str,
        work_type: str,
        age_seconds: float,
    ) -> None:
        """Record the age of a retried work item when it is claimed again."""

        if not self.enabled:
            return
        retry_age = self._fact_resolution_instruments.get("fact_queue_retry_age")
        if retry_age is not None:
            retry_age.record(
                age_seconds,
                {
                    "pcg.component": component,
                    "pcg.work_type": work_type,
                },
            )

    def record_fact_queue_dead_letter(
        self,
        *,
        component: str,
        work_type: str,
        error_class: str,
        age_seconds: float | None,
    ) -> None:
        """Record one dead-lettered work item and its age when known."""

        if not self.enabled:
            return
        dead_letters_total = self._fact_resolution_instruments.get(
            "fact_queue_dead_letters_total"
        )
        dead_letter_age = self._fact_resolution_instruments.get(
            "fact_queue_dead_letter_age"
        )
        attrs = {
            "pcg.component": component,
            "pcg.work_type": work_type,
            "pcg.error_class": error_class,
        }
        if dead_letters_total is not None:
            dead_letters_total.add(1, attrs)
        if age_seconds is not None and dead_letter_age is not None:
            dead_letter_age.record(
                age_seconds,
                {
                    "pcg.component": component,
                    "pcg.work_type": work_type,
                },
            )


def _pool_key(component: str, pool_name: str) -> tuple[tuple[str, str], ...]:
    """Return a stable low-cardinality key for one pool."""

    return tuple(
        sorted(
            {
                "pcg.component": component,
                "pcg.pool": pool_name,
            }.items()
        )
    )


def set_fact_postgres_pool_stats(
    *,
    component: str,
    pool_name: str,
    size: int,
    available: int,
    waiting: int,
) -> None:
    """Store the latest fact-postgres pool stats for observable gauges."""

    key = _pool_key(component, pool_name)
    with _POOL_LOCK:
        _POOL_SIZE[key] = max(size, 0)
        _POOL_AVAILABLE[key] = max(available, 0)
        _POOL_WAITING[key] = max(waiting, 0)


def observe_fact_postgres_pool_size(_options: Any) -> list[Observation]:
    """Produce sampled pool size observations."""

    with _POOL_LOCK:
        return [
            Observation(value, dict(key)) for key, value in sorted(_POOL_SIZE.items())
        ]


def observe_fact_postgres_pool_available(_options: Any) -> list[Observation]:
    """Produce sampled pool available-connection observations."""

    with _POOL_LOCK:
        return [
            Observation(value, dict(key))
            for key, value in sorted(_POOL_AVAILABLE.items())
        ]


def observe_fact_postgres_pool_in_use(_options: Any) -> list[Observation]:
    """Produce sampled pool in-use connection observations."""

    with _POOL_LOCK:
        observations: list[Observation] = []
        for key in sorted(_POOL_SIZE):
            size = _POOL_SIZE.get(key, 0)
            available = _POOL_AVAILABLE.get(key, 0)
            observations.append(Observation(max(size - available, 0), dict(key)))
        return observations


def observe_fact_postgres_pool_waiting(_options: Any) -> list[Observation]:
    """Produce sampled pool waiting-request observations."""

    with _POOL_LOCK:
        return [
            Observation(value, dict(key))
            for key, value in sorted(_POOL_WAITING.items())
        ]


def setup_fact_scaling_instruments(runtime: Any) -> None:
    """Register scaling-specific telemetry instruments for one runtime."""

    if not runtime.enabled or runtime.meter is None:
        return

    instruments = runtime._fact_resolution_instruments
    instruments["fact_postgres_pool_acquire_duration"] = runtime.meter.create_histogram(
        "pcg_fact_postgres_pool_acquire_duration_seconds",
        unit="s",
    )
    instruments["fact_queue_retry_age"] = runtime.meter.create_histogram(
        "pcg_fact_queue_retry_age_seconds",
        unit="s",
    )
    instruments["fact_queue_dead_letters_total"] = runtime.meter.create_counter(
        "pcg_fact_queue_dead_letters_total"
    )
    instruments["fact_queue_dead_letter_age"] = runtime.meter.create_histogram(
        "pcg_fact_queue_dead_letter_age_seconds",
        unit="s",
    )
    runtime.meter.create_observable_gauge(
        "pcg_fact_postgres_pool_size",
        callbacks=[observe_fact_postgres_pool_size],
    )
    runtime.meter.create_observable_gauge(
        "pcg_fact_postgres_pool_available",
        callbacks=[observe_fact_postgres_pool_available],
    )
    runtime.meter.create_observable_gauge(
        "pcg_fact_postgres_pool_in_use",
        callbacks=[observe_fact_postgres_pool_in_use],
    )
    runtime.meter.create_observable_gauge(
        "pcg_fact_postgres_pool_waiting",
        callbacks=[observe_fact_postgres_pool_waiting],
    )


__all__ = [
    "RuntimeFactScalingMetricsMixin",
    "set_fact_postgres_pool_stats",
    "setup_fact_scaling_instruments",
]

"""Observable-gauge helpers for facts-first telemetry."""

from __future__ import annotations

import threading
from typing import Any

from .otel import Observation


class RuntimeFactResolutionObserverMixin:
    """Provide observable callbacks for facts-first queue gauges."""

    _lock: threading.Lock
    _fact_queue_depth: dict[tuple[tuple[str, str], ...], int]
    _fact_queue_oldest_age_seconds: dict[tuple[tuple[str, str], ...], float]
    _resolution_workers_active: dict[tuple[tuple[str, str], ...], int]

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

    def _observe_resolution_workers_active(self, _options: Any) -> list[Observation]:
        """Produce current resolution worker active-count observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._resolution_workers_active.items())
            ]

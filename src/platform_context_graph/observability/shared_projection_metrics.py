"""Shared-projection backlog telemetry helpers."""

from __future__ import annotations

import threading
from typing import Any


class RuntimeSharedProjectionMetricsMixin:
    """Provide shared-projection backlog metric helpers."""

    enabled: bool
    _lock: threading.Lock
    _shared_projection_pending_intents: dict[tuple[tuple[str, str], ...], int]
    _shared_projection_oldest_pending_age_seconds: dict[
        tuple[tuple[str, str], ...], float
    ]

    def replace_shared_projection_backlog(
        self,
        *,
        component: str,
        snapshot_rows: list[Any],
    ) -> None:
        """Replace shared-projection backlog gauges for one component."""

        pending_updates: dict[tuple[tuple[str, str], ...], int] = {}
        age_updates: dict[tuple[tuple[str, str], ...], float] = {}
        for row in snapshot_rows:
            projection_domain = str(getattr(row, "projection_domain", "") or "").strip()
            if not projection_domain:
                continue
            key = tuple(
                sorted(
                    {
                        "pcg.component": component,
                        "pcg.projection_domain": projection_domain,
                    }.items()
                )
            )
            pending_depth = int(getattr(row, "pending_depth", 0) or 0)
            oldest_age_seconds = float(getattr(row, "oldest_age_seconds", 0.0) or 0.0)
            if pending_depth > 0:
                pending_updates[key] = pending_depth
            if oldest_age_seconds > 0:
                age_updates[key] = oldest_age_seconds

        with self._lock:
            for key in list(self._shared_projection_pending_intents):
                if dict(key).get("pcg.component") == component:
                    self._shared_projection_pending_intents.pop(key, None)
            self._shared_projection_pending_intents.update(pending_updates)

            for key in list(self._shared_projection_oldest_pending_age_seconds):
                if dict(key).get("pcg.component") == component:
                    self._shared_projection_oldest_pending_age_seconds.pop(key, None)
            self._shared_projection_oldest_pending_age_seconds.update(age_updates)

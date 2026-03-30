"""Indexing-specific metric helpers for the observability runtime."""

from __future__ import annotations

import threading
from typing import Any

from .otel import Observation


_MEMORY_UNSET = -1


class RuntimeIndexMetricsMixin:
    """Provide indexing metric helpers for :class:`ObservabilityRuntime`."""

    enabled: bool
    _lock: threading.Lock
    _active_runs: dict[tuple[tuple[str, str], ...], int]
    _active_repositories: dict[tuple[tuple[str, str], ...], int]
    _checkpoint_pending_repositories: dict[tuple[tuple[str, str], ...], int]
    _index_snapshot_queue_depth: dict[tuple[tuple[str, str], ...], int]
    _index_parse_tasks_active: dict[tuple[tuple[str, str], ...], int]
    _process_rss_bytes: int
    _cgroup_memory_bytes: int
    _cgroup_memory_limit_bytes: int
    index_repositories_total: Any
    index_checkpoints_total: Any
    index_repository_duration: Any
    index_stage_duration: Any
    index_lock_contention_skips_total: Any

    def record_index_repositories(
        self,
        *,
        component: str,
        phase: str,
        count: int,
        mode: str,
        source: str,
    ) -> None:
        """Record repository counts for a phase of an index run."""

        if not self.enabled or self.index_repositories_total is None:
            return
        self.index_repositories_total.add(
            count,
            {
                "component": component,
                "phase": phase,
                "mode": mode,
                "source": source,
            },
        )

    def record_index_checkpoint(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        operation: str,
        status: str,
    ) -> None:
        """Record a checkpoint lifecycle event for an index run."""

        if not self.enabled or self.index_checkpoints_total is None:
            return
        self.index_checkpoints_total.add(
            1,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "operation": operation,
                "status": status,
            },
        )

    def record_index_repository_duration(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        """Record the duration of one repository parse or commit attempt."""

        if not self.enabled or self.index_repository_duration is None:
            return
        self.index_repository_duration.record(
            duration_seconds,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "status": status,
            },
        )

    def record_index_stage_duration(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        stage: str,
        duration_seconds: float,
        parse_strategy: str,
        parse_workers: int,
    ) -> None:
        """Record queue, parse, commit, or finalization stage duration."""

        if not self.enabled or self.index_stage_duration is None:
            return
        self.index_stage_duration.record(
            duration_seconds,
            {
                "component": component,
                "mode": mode,
                "source": source,
                "stage": stage,
                "parse_strategy": parse_strategy,
                "parse_workers": str(parse_workers),
            },
        )

    def set_index_snapshot_queue_depth(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        depth: int,
        parse_strategy: str,
        parse_workers: int,
    ) -> None:
        """Set the observable queue depth for parsed repositories awaiting commit."""

        key = tuple(
            sorted(
                {
                    "component": component,
                    "mode": mode,
                    "source": source,
                    "parse_strategy": parse_strategy,
                    "parse_workers": str(parse_workers),
                }.items()
            )
        )
        with self._lock:
            if depth <= 0:
                self._index_snapshot_queue_depth.pop(key, None)
            else:
                self._index_snapshot_queue_depth[key] = depth

    def set_index_parse_tasks_active(
        self,
        *,
        component: str,
        mode: str,
        source: str,
        active_count: int,
        parse_strategy: str,
        parse_workers: int,
    ) -> None:
        """Set the observable number of in-flight file parse tasks."""

        key = tuple(
            sorted(
                {
                    "component": component,
                    "mode": mode,
                    "source": source,
                    "parse_strategy": parse_strategy,
                    "parse_workers": str(parse_workers),
                }.items()
            )
        )
        with self._lock:
            if active_count <= 0:
                self._index_parse_tasks_active.pop(key, None)
            else:
                self._index_parse_tasks_active[key] = active_count

    def record_lock_contention_skip(
        self,
        *,
        component: str,
        mode: str,
        source: str,
    ) -> None:
        """Record a skipped index run due to lock contention."""

        if not self.enabled or self.index_lock_contention_skips_total is None:
            return
        self.index_lock_contention_skips_total.add(
            1,
            {
                "component": component,
                "mode": mode,
                "source": source,
            },
        )

    def _adjust_active_state(
        self,
        key: tuple[tuple[str, str], ...],
        *,
        runs_delta: int = 0,
        repos_delta: int = 0,
    ) -> None:
        """Update the active-run and active-repository gauge state."""

        with self._lock:
            if runs_delta:
                new_runs = self._active_runs.get(key, 0) + runs_delta
                if new_runs <= 0:
                    self._active_runs.pop(key, None)
                else:
                    self._active_runs[key] = new_runs
            if repos_delta:
                new_repos = self._active_repositories.get(key, 0) + repos_delta
                if new_repos <= 0:
                    self._active_repositories.pop(key, None)
                else:
                    self._active_repositories[key] = new_repos

    def _observe_active_runs(self, _options: Any) -> list[Observation]:
        """Produce current active-run gauge observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._active_runs.items())
            ]

    def _observe_active_repositories(self, _options: Any) -> list[Observation]:
        """Produce current active-repository gauge observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._active_repositories.items())
            ]

    def _observe_pending_checkpoint_repositories(
        self, _options: Any
    ) -> list[Observation]:
        """Produce current pending-checkpoint repository gauge observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._checkpoint_pending_repositories.items())
            ]

    def _observe_index_snapshot_queue_depth(self, _options: Any) -> list[Observation]:
        """Produce current parsed-repository queue depth observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._index_snapshot_queue_depth.items())
            ]

    def _observe_index_parse_tasks_active(self, _options: Any) -> list[Observation]:
        """Produce current in-flight file parse task observations."""

        with self._lock:
            return [
                Observation(value, dict(key))
                for key, value in sorted(self._index_parse_tasks_active.items())
            ]

    def record_memory_usage(self, sample: Any) -> None:
        """Store the latest memory sample for gauge observation."""

        if sample.rss_bytes is not None:
            self._process_rss_bytes = sample.rss_bytes
        if sample.cgroup_memory_bytes is not None:
            self._cgroup_memory_bytes = sample.cgroup_memory_bytes
        if getattr(sample, "cgroup_memory_limit_bytes", None) is not None:
            self._cgroup_memory_limit_bytes = sample.cgroup_memory_limit_bytes

    def _make_memory_observer(self, attr_name: str) -> Any:
        """Return a gauge callback that reads one memory field by attribute name."""

        def _observe(_options: Any) -> list[Observation]:
            """Yield one gauge observation when the memory sample is populated."""

            value = getattr(self, attr_name, _MEMORY_UNSET)
            return [] if value == _MEMORY_UNSET else [Observation(value, {})]

        return _observe

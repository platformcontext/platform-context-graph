"""Runtime shell for the Phase 2 Resolution Engine."""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
from collections.abc import Callable

from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.observability import get_observability
from platform_context_graph.observability import initialize_observability

from .engine import project_work_item

ProjectorFn = Callable[[FactWorkItemRow], None]


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def _refresh_queue_metrics(queue: object) -> None:
    """Update queue depth and lag gauges when the queue supports snapshots."""

    snapshot_fn = getattr(queue, "list_queue_snapshot", None)
    if not callable(snapshot_fn):
        return
    observability = get_observability()
    for row in snapshot_fn():
        observability.set_fact_queue_depth(
            component="resolution-engine",
            work_type=row.work_type,
            status=row.status,
            depth=row.depth,
        )
        observability.set_fact_queue_oldest_age_seconds(
            component="resolution-engine",
            work_type=row.work_type,
            status=row.status,
            age_seconds=row.oldest_age_seconds,
        )
    refresh_pool_metrics = getattr(queue, "refresh_pool_metrics", None)
    if callable(refresh_pool_metrics):
        refresh_pool_metrics(component="resolution-engine")


def run_queue_metrics_sampler_once(*, queue: object) -> None:
    """Sample queue depth and pool metrics independently of work processing."""

    _refresh_queue_metrics(queue)


def _run_queue_metrics_sampler(
    *,
    queue: object,
    stop_event: threading.Event,
    interval_seconds: float,
) -> None:
    """Refresh queue metrics on an independent cadence until stopped."""

    while not stop_event.is_set():
        run_queue_metrics_sampler_once(queue=queue)
        if stop_event.wait(max(interval_seconds, 0.1)):
            return


def run_resolution_iteration(
    *,
    queue: object,
    projector: ProjectorFn = project_work_item,
    lease_owner: str,
    lease_ttl_seconds: int,
    max_attempts: int = 3,
) -> bool:
    """Claim and process at most one resolution work item.

    Args:
        queue: Queue object exposing `claim_work_item`, `complete_work_item`,
            and `fail_work_item`.
        projector: Callable that projects one claimed work item.
        lease_owner: Worker identity used when claiming a lease.
        lease_ttl_seconds: Lease duration for the claimed work item.

    Returns:
        `True` when a work item was claimed, else `False`.
    """

    observability = get_observability()
    iteration_started = time.perf_counter()
    with observability.start_span(
        "pcg.resolution.iteration",
        component="resolution-engine",
        attributes={
            "pcg.queue.lease_owner": lease_owner,
            "pcg.queue.lease_ttl_seconds": lease_ttl_seconds,
        },
    ):
        claim_started = time.perf_counter()
        work_item = queue.claim_work_item(
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
        )
        claim_duration = max(time.perf_counter() - claim_started, 0.0)
        _refresh_queue_metrics(queue)
        if work_item is None:
            observability.set_resolution_workers_active(
                component="resolution-engine",
                active_count=0,
            )
            observability.record_resolution_claim(
                component="resolution-engine",
                work_type="none",
                outcome="empty",
                duration_seconds=claim_duration,
            )
            observability.record_resolution_work_item(
                component="resolution-engine",
                work_type="none",
                outcome="empty",
                duration_seconds=max(time.perf_counter() - iteration_started, 0.0),
            )
            return False

        observability.record_resolution_claim(
            component="resolution-engine",
            work_type=work_item.work_type,
            outcome="claimed",
            duration_seconds=claim_duration,
        )
        work_item_age_seconds: float | None = None
        if work_item.created_at is not None:
            work_item_age_seconds = max(
                (_utc_now() - work_item.created_at).total_seconds(),
                0.0,
            )
        if work_item.attempt_count > 1 and work_item_age_seconds is not None:
            observability.record_fact_queue_retry_age(
                component="resolution-engine",
                work_type=work_item.work_type,
                age_seconds=work_item_age_seconds,
            )
        observability.set_resolution_workers_active(
            component="resolution-engine",
            active_count=1,
        )
        try:
            projector(work_item)
        except Exception as exc:
            terminal = work_item.attempt_count >= max_attempts
            queue.fail_work_item(
                work_item_id=work_item.work_item_id,
                error_message=str(exc),
                terminal=terminal,
            )
            if terminal:
                observability.record_fact_queue_dead_letter(
                    component="resolution-engine",
                    work_type=work_item.work_type,
                    error_class=type(exc).__name__,
                    age_seconds=work_item_age_seconds,
                )
            _refresh_queue_metrics(queue)
            observability.record_resolution_work_item(
                component="resolution-engine",
                work_type=work_item.work_type,
                outcome="failed",
                duration_seconds=max(time.perf_counter() - iteration_started, 0.0),
            )
        else:
            queue.complete_work_item(work_item_id=work_item.work_item_id)
            _refresh_queue_metrics(queue)
            observability.record_resolution_work_item(
                component="resolution-engine",
                work_type=work_item.work_type,
                outcome="completed",
                duration_seconds=max(time.perf_counter() - iteration_started, 0.0),
            )
        finally:
            observability.set_resolution_workers_active(
                component="resolution-engine",
                active_count=0,
            )

    return True


def start_resolution_engine(
    *,
    queue: object,
    lease_owner: str = "resolution-engine",
    lease_ttl_seconds: int = 60,
    max_attempts: int = 3,
    idle_sleep_seconds: float = 1.0,
    queue_metrics_refresh_seconds: float = 15.0,
    run_once: bool = False,
    projector: ProjectorFn = project_work_item,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Run the long-lived Resolution Engine loop.

    Args:
        queue: Queue object used for claim/complete/fail operations.
        lease_owner: Worker identity used when claiming leases.
        lease_ttl_seconds: Lease duration in seconds.
        idle_sleep_seconds: Sleep duration between empty polls.
        run_once: Whether to stop after a single iteration.
        projector: Callable that projects one claimed work item.
        sleep_fn: Sleep function injected for tests.
    """

    initialize_observability(component="resolution-engine")
    sampler_stop = threading.Event()
    sampler_thread: threading.Thread | None = None
    if not run_once:
        sampler_thread = threading.Thread(
            target=_run_queue_metrics_sampler,
            kwargs={
                "queue": queue,
                "stop_event": sampler_stop,
                "interval_seconds": queue_metrics_refresh_seconds,
            },
            name="pcg-resolution-queue-metrics",
            daemon=True,
        )
        sampler_thread.start()
    try:
        while True:
            processed = run_resolution_iteration(
                queue=queue,
                projector=projector,
                lease_owner=lease_owner,
                lease_ttl_seconds=lease_ttl_seconds,
                max_attempts=max_attempts,
            )
            if run_once:
                return
            if not processed:
                sleep_started = time.perf_counter()
                try:
                    sleep_fn(idle_sleep_seconds)
                finally:
                    get_observability().record_resolution_idle_sleep(
                        component="resolution-engine",
                        duration_seconds=max(time.perf_counter() - sleep_started, 0.0),
                    )
    finally:
        sampler_stop.set()
        if sampler_thread is not None:
            sampler_thread.join(timeout=max(queue_metrics_refresh_seconds, 0.1) * 2)

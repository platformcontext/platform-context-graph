"""Runtime shell for the Phase 2 Resolution Engine."""

from __future__ import annotations

import time
from collections.abc import Callable

from platform_context_graph.facts.work_queue.models import FactWorkItemRow

from .engine import project_work_item

ProjectorFn = Callable[[FactWorkItemRow], None]


def run_resolution_iteration(
    *,
    queue: object,
    projector: ProjectorFn = project_work_item,
    lease_owner: str,
    lease_ttl_seconds: int,
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

    work_item = queue.claim_work_item(
        lease_owner=lease_owner,
        lease_ttl_seconds=lease_ttl_seconds,
    )
    if work_item is None:
        return False

    try:
        projector(work_item)
    except Exception as exc:
        queue.fail_work_item(
            work_item_id=work_item.work_item_id,
            error_message=str(exc),
            terminal=False,
        )
    else:
        queue.complete_work_item(work_item_id=work_item.work_item_id)

    return True


def start_resolution_engine(
    *,
    queue: object,
    lease_owner: str = "resolution-engine",
    lease_ttl_seconds: int = 60,
    idle_sleep_seconds: float = 1.0,
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

    while True:
        processed = run_resolution_iteration(
            queue=queue,
            projector=projector,
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
        )
        if run_once:
            return
        if not processed:
            sleep_fn(idle_sleep_seconds)

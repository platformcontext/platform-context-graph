"""Shared-projection completion helpers for facts-first commits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .commit_timing import CommitTimingResult


@dataclass(frozen=True, slots=True)
class SharedProjectionCompletionState:
    """Completion state for authoritative shared follow-up after repo-local writes."""

    authoritative_domains: tuple[str, ...] = ()
    accepted_generation_id: str | None = None

    @property
    def pending(self) -> bool:
        """Return whether authoritative shared follow-up still blocks completion."""

        return bool(self.authoritative_domains)


def completion_state_from_metrics(
    metrics: dict[str, Any] | None, *, default_generation_id: str
) -> SharedProjectionCompletionState:
    """Extract authoritative shared-follow-up requirements from projection metrics."""

    if not isinstance(metrics, dict):
        return SharedProjectionCompletionState()
    payload = metrics.get("shared_projection")
    if not isinstance(payload, dict):
        nested_platform_metrics = metrics.get("platforms")
        if isinstance(nested_platform_metrics, dict):
            payload = nested_platform_metrics.get("shared_projection")
    if not isinstance(payload, dict):
        return SharedProjectionCompletionState()
    raw_domains = payload.get("authoritative_domains")
    if not isinstance(raw_domains, (list, tuple)):
        return SharedProjectionCompletionState()
    domains = tuple(
        sorted({str(domain).strip() for domain in raw_domains if str(domain).strip()})
    )
    if not domains:
        return SharedProjectionCompletionState()
    accepted_generation_id = str(payload.get("accepted_generation_id") or "").strip()
    if not accepted_generation_id:
        accepted_generation_id = default_generation_id.strip()
    if not accepted_generation_id:
        return SharedProjectionCompletionState()
    return SharedProjectionCompletionState(
        authoritative_domains=domains,
        accepted_generation_id=accepted_generation_id,
    )


def apply_completion_state(
    *,
    queue: Any,
    work_item_id: str,
    completion_state: SharedProjectionCompletionState,
) -> None:
    """Persist the work-item completion fence for authoritative shared follow-up."""

    if completion_state.pending:
        queue.mark_shared_projection_pending(
            work_item_id=work_item_id,
            accepted_generation_id=completion_state.accepted_generation_id or "",
            authoritative_shared_domains=list(completion_state.authoritative_domains),
        )
        return
    queue.complete_work_item(work_item_id=work_item_id)


def decorate_timing_result(
    timing: CommitTimingResult,
    *,
    completion_state: SharedProjectionCompletionState,
) -> CommitTimingResult:
    """Copy shared-follow-up completion metadata onto one timing result."""

    timing.shared_projection_pending = completion_state.pending
    timing.authoritative_shared_domains = completion_state.authoritative_domains
    timing.accepted_generation_id = completion_state.accepted_generation_id
    return timing

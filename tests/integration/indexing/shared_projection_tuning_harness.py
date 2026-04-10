"""Deterministic tuning helpers for shared-projection load validation."""

from __future__ import annotations

from dataclasses import dataclass

from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionIntentRow,
)


@dataclass(frozen=True, slots=True)
class TuningScenarioResult:
    """One deterministic shared-write tuning outcome."""

    partition_count: int
    batch_limit: int
    round_count: int
    processed_total: int
    peak_pending_total: int
    mean_processed_per_round: float


def sweep_tuning_candidates(
    *,
    rows: list[SharedProjectionIntentRow],
    projection_domains: list[str],
    candidates: list[tuple[int, int]],
    max_rounds: int = 20,
) -> list[TuningScenarioResult]:
    """Return deterministic outcomes for one candidate setting list."""

    from tests.integration.indexing.shared_projection_load_harness import (
        InMemorySharedIntentStore,
    )
    from tests.integration.indexing.shared_projection_load_harness import (
        SharedProjectionQueue,
    )
    from tests.integration.indexing.shared_projection_load_harness import (
        drain_until_empty,
    )

    results: list[TuningScenarioResult] = []
    initial_pending_total = len(rows)
    for partition_count, batch_limit in candidates:
        store = InMemorySharedIntentStore(list(rows))
        queue = SharedProjectionQueue(store)
        rounds = drain_until_empty(
            shared_projection_intent_store=store,
            fact_work_queue=queue,
            projection_domains=projection_domains,
            partition_count=partition_count,
            batch_limit=batch_limit,
            max_rounds=max_rounds,
        )
        processed_total = sum(round_state.processed_total for round_state in rounds)
        peak_pending_total = max(
            [initial_pending_total]
            + [round_state.pending_total for round_state in rounds]
        )
        round_count = len(rounds)
        results.append(
            TuningScenarioResult(
                partition_count=partition_count,
                batch_limit=batch_limit,
                round_count=round_count,
                processed_total=processed_total,
                peak_pending_total=peak_pending_total,
                mean_processed_per_round=processed_total / round_count,
            )
        )
    return results


def select_preferred_tuning_scenario(
    scenarios: list[TuningScenarioResult],
) -> TuningScenarioResult:
    """Return the preferred scenario using stable tuning priorities."""

    if not scenarios:
        raise ValueError("at least one tuning scenario is required")
    return min(
        scenarios,
        key=lambda scenario: (
            scenario.round_count,
            -scenario.mean_processed_per_round,
            scenario.partition_count,
            scenario.batch_limit,
        ),
    )

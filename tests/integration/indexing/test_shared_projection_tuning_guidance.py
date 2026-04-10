"""Integration checks for shared-write tuning guidance helpers."""

from __future__ import annotations

from tests.integration.indexing.shared_projection_load_harness import (
    build_balanced_intents,
)
from tests.integration.indexing.shared_projection_tuning_harness import (
    TuningScenarioResult,
)
from tests.integration.indexing.shared_projection_tuning_harness import (
    select_preferred_tuning_scenario,
)
from tests.integration.indexing.shared_projection_tuning_harness import (
    sweep_tuning_candidates,
)


def test_sweep_tuning_candidates_compares_partition_and_batch_settings() -> None:
    """The tuning sweep should compare deterministic drain outcomes."""

    rows = build_balanced_intents(
        projection_domain="repo_dependency",
        partition_count=4,
        intents_per_partition=4,
        source_run_id="run-tuning",
    ) + build_balanced_intents(
        projection_domain="workload_dependency",
        partition_count=4,
        intents_per_partition=4,
        source_run_id="run-tuning",
    )

    results = sweep_tuning_candidates(
        rows=rows,
        projection_domains=["repo_dependency", "workload_dependency"],
        candidates=[
            (1, 1),
            (2, 1),
            (4, 1),
            (4, 2),
        ],
    )

    assert [(result.partition_count, result.batch_limit) for result in results] == [
        (1, 1),
        (2, 1),
        (4, 1),
        (4, 2),
    ]
    assert all(result.processed_total == len(rows) for result in results)
    assert all(result.peak_pending_total == len(rows) for result in results)
    assert results[0].round_count > results[1].round_count >= results[2].round_count
    assert results[2].round_count >= results[3].round_count
    assert (
        results[0].mean_processed_per_round
        < results[1].mean_processed_per_round
        <= results[2].mean_processed_per_round
        <= results[3].mean_processed_per_round
    )


def test_select_preferred_tuning_scenario_prefers_rounds_then_throughput() -> None:
    """Recommendation should minimize drain rounds before chasing throughput."""

    baseline = TuningScenarioResult(
        partition_count=2,
        batch_limit=1,
        round_count=5,
        processed_total=20,
        peak_pending_total=20,
        mean_processed_per_round=4.0,
    )
    better_rounds = TuningScenarioResult(
        partition_count=4,
        batch_limit=1,
        round_count=3,
        processed_total=20,
        peak_pending_total=20,
        mean_processed_per_round=6.67,
    )
    better_throughput = TuningScenarioResult(
        partition_count=4,
        batch_limit=2,
        round_count=3,
        processed_total=20,
        peak_pending_total=20,
        mean_processed_per_round=8.0,
    )

    assert (
        select_preferred_tuning_scenario([baseline, better_rounds, better_throughput])
        == better_throughput
    )

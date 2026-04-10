"""Support helpers for the shared projection tuning report script."""

from __future__ import annotations

from typing import Any

from platform_context_graph.resolution.shared_projection.runtime import (
    PLATFORM_INFRA_PROJECTION_DOMAIN,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    REPO_DEPENDENCY_PROJECTION_DOMAIN,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
)
from tests.integration.indexing.shared_projection_load_harness import (
    build_balanced_intents,
)
from tests.integration.indexing.shared_projection_tuning_harness import (
    select_preferred_tuning_scenario,
)
from tests.integration.indexing.shared_projection_tuning_harness import (
    sweep_tuning_candidates,
)

DEFAULT_CANDIDATES: tuple[tuple[int, int], ...] = (
    (1, 1),
    (2, 1),
    (4, 1),
    (4, 2),
)
DEFAULT_SEED_PARTITIONS = 4
DEFAULT_INTENTS_PER_PARTITION = 4


def projection_domains_for_report(*, include_platform: bool) -> list[str]:
    """Return the ordered projection domains for the local tuning report."""

    domains = [
        REPO_DEPENDENCY_PROJECTION_DOMAIN,
        WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
    ]
    if include_platform:
        return [PLATFORM_INFRA_PROJECTION_DOMAIN, *domains]
    return domains


def build_tuning_report(
    *,
    include_platform: bool = False,
    candidates: list[tuple[int, int]] | None = None,
    seed_partitions: int = DEFAULT_SEED_PARTITIONS,
    intents_per_partition: int = DEFAULT_INTENTS_PER_PARTITION,
) -> dict[str, Any]:
    """Return one deterministic shared-write tuning report payload."""

    projection_domains = projection_domains_for_report(
        include_platform=include_platform
    )
    seeded_rows = []
    for projection_domain in projection_domains:
        seeded_rows.extend(
            build_balanced_intents(
                projection_domain=projection_domain,
                partition_count=seed_partitions,
                intents_per_partition=intents_per_partition,
                source_run_id="run-tuning-report",
            )
        )
    scenario_rows = sweep_tuning_candidates(
        rows=seeded_rows,
        projection_domains=projection_domains,
        candidates=list(candidates or DEFAULT_CANDIDATES),
    )
    recommended = select_preferred_tuning_scenario(scenario_rows)
    return {
        "projection_domains": projection_domains,
        "seed_partitions": seed_partitions,
        "intents_per_partition": intents_per_partition,
        "scenarios": [
            {
                "setting": f"{scenario.partition_count}x{scenario.batch_limit}",
                "partition_count": scenario.partition_count,
                "batch_limit": scenario.batch_limit,
                "round_count": scenario.round_count,
                "processed_total": scenario.processed_total,
                "peak_pending_total": scenario.peak_pending_total,
                "mean_processed_per_round": round(scenario.mean_processed_per_round, 2),
            }
            for scenario in scenario_rows
        ],
        "recommended": {
            "setting": f"{recommended.partition_count}x{recommended.batch_limit}",
            "partition_count": recommended.partition_count,
            "batch_limit": recommended.batch_limit,
            "round_count": recommended.round_count,
            "processed_total": recommended.processed_total,
            "peak_pending_total": recommended.peak_pending_total,
            "mean_processed_per_round": round(recommended.mean_processed_per_round, 2),
        },
    }

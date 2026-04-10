"""Integration checks for deterministic shared-write load validation."""

from __future__ import annotations

from typing import Any

import pytest

from platform_context_graph.observability import initialize_observability
from platform_context_graph.observability import reset_observability_for_tests
from platform_context_graph.query.status_shared_projection import (
    enrich_shared_projection_status,
)
from platform_context_graph.resolution.orchestration import runtime as runtime_mod
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
    SharedProjectionQueue,
)
from tests.integration.indexing.shared_projection_load_harness import (
    InMemorySharedIntentStore,
)
from tests.integration.indexing.shared_projection_load_harness import (
    build_balanced_intents,
)
from tests.integration.indexing.shared_projection_load_harness import (
    drain_until_empty,
)
from tests.integration.indexing.shared_projection_load_harness import (
    matching_metric_values,
)
from tests.integration.indexing.shared_projection_load_harness import metric_points


def _pending_totals(rounds: list[Any]) -> list[int]:
    """Return total pending counts after each drain round."""

    return [int(round_state.pending_total) for round_state in rounds]


def test_partitioned_dependency_drain_reduces_rounds_and_clears_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Balanced dependency backlogs should drain faster with more partitions."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
    )
    monkeypatch.setattr(
        runtime_mod,
        "get_shared_projection_intent_store",
        lambda: None,
        raising=False,
    )

    rows = build_balanced_intents(
        projection_domain=REPO_DEPENDENCY_PROJECTION_DOMAIN,
        partition_count=4,
        intents_per_partition=4,
        source_run_id="run-load",
    ) + build_balanced_intents(
        projection_domain=WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
        partition_count=4,
        intents_per_partition=4,
        source_run_id="run-load",
    )
    single_store = InMemorySharedIntentStore(rows)
    single_queue = SharedProjectionQueue(single_store)
    multi_store = InMemorySharedIntentStore(rows)
    multi_queue = SharedProjectionQueue(multi_store)

    runtime_mod.run_queue_metrics_sampler_once(queue=multi_queue)
    before_points = metric_points(metric_reader)
    single_rounds = drain_until_empty(
        shared_projection_intent_store=single_store,
        fact_work_queue=single_queue,
        projection_domains=[
            REPO_DEPENDENCY_PROJECTION_DOMAIN,
            WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
        ],
        partition_count=1,
        batch_limit=2,
    )
    multi_rounds = drain_until_empty(
        shared_projection_intent_store=multi_store,
        fact_work_queue=multi_queue,
        projection_domains=[
            REPO_DEPENDENCY_PROJECTION_DOMAIN,
            WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
        ],
        partition_count=4,
        batch_limit=2,
        sampler=lambda: runtime_mod.run_queue_metrics_sampler_once(queue=multi_queue),
    )
    after_points = metric_points(metric_reader)

    assert len(multi_rounds) < len(single_rounds)
    assert _pending_totals(multi_rounds) == sorted(
        _pending_totals(multi_rounds), reverse=True
    )
    assert multi_rounds[-1].pending_total == 0
    assert sum(round_state.processed_total for round_state in multi_rounds) == len(rows)
    assert matching_metric_values(
        before_points,
        "pcg_shared_projection_pending_intents",
        **{
            "pcg.component": "resolution-engine",
            "pcg.projection_domain": REPO_DEPENDENCY_PROJECTION_DOMAIN,
        },
    ) == [16]
    assert matching_metric_values(
        before_points,
        "pcg_shared_projection_pending_intents",
        **{
            "pcg.component": "resolution-engine",
            "pcg.projection_domain": WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
        },
    ) == [16]
    assert (
        matching_metric_values(
            after_points,
            "pcg_shared_projection_pending_intents",
            **{
                "pcg.component": "resolution-engine",
                "pcg.projection_domain": REPO_DEPENDENCY_PROJECTION_DOMAIN,
            },
        )
        == []
    )
    assert (
        matching_metric_values(
            after_points,
            "pcg_shared_projection_pending_intents",
            **{
                "pcg.component": "resolution-engine",
                "pcg.projection_domain": WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
            },
        )
        == []
    )


def test_mixed_domain_status_backlog_tracks_round_based_drain() -> None:
    """Status backlog should track mixed shared domains until the drain completes."""

    rows = (
        build_balanced_intents(
            projection_domain=PLATFORM_INFRA_PROJECTION_DOMAIN,
            partition_count=2,
            intents_per_partition=2,
            source_run_id="run-status",
        )
        + build_balanced_intents(
            projection_domain=REPO_DEPENDENCY_PROJECTION_DOMAIN,
            partition_count=2,
            intents_per_partition=2,
            source_run_id="run-status",
        )
        + build_balanced_intents(
            projection_domain=WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
            partition_count=2,
            intents_per_partition=2,
            source_run_id="run-status",
        )
    )
    store = InMemorySharedIntentStore(rows)
    queue = SharedProjectionQueue(store)
    base_payload = {
        "active_run_id": "run-status",
        "status": "completed",
        "completed_repositories": 3,
        "in_sync_repositories": 3,
        "pending_repositories": 0,
    }

    rounds = drain_until_empty(
        shared_projection_intent_store=store,
        fact_work_queue=queue,
        projection_domains=[
            PLATFORM_INFRA_PROJECTION_DOMAIN,
            REPO_DEPENDENCY_PROJECTION_DOMAIN,
            WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
        ],
        partition_count=2,
        batch_limit=1,
        status_payload=base_payload,
    )

    assert rounds[0].status_payload["status"] == "indexing"
    assert rounds[0].status_payload["active_phase"] == "awaiting_shared_projection"
    assert rounds[0].status_payload["shared_projection_backlog"]
    assert rounds[-1].pending_total == 0
    assert rounds[-1].status_payload == enrich_shared_projection_status(
        base_payload,
        queue=queue,
        shared_projection_intent_store=store,
    )
    assert rounds[-1].status_payload["shared_projection_backlog"] == []
    assert rounds[-1].status_payload["shared_projection_pending_repositories"] == 0

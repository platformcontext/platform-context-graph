"""Deterministic shared-write tuning report helpers."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from datetime import datetime
from datetime import timezone
from typing import Any

from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionBacklogSnapshotRow,
)
from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionIntentRow,
)
from platform_context_graph.resolution.shared_projection.models import (
    build_shared_projection_intent,
)
from platform_context_graph.resolution.shared_projection.partitioning import (
    partition_for_key,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    PLATFORM_INFRA_PROJECTION_DOMAIN,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    REPO_DEPENDENCY_PROJECTION_DOMAIN,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    process_dependency_partition_once,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    process_platform_partition_once,
)

from .shared_projection_tuning_format import format_tuning_report_table

DEFAULT_CANDIDATES: tuple[tuple[int, int], ...] = (
    (1, 1),
    (2, 1),
    (4, 1),
    (4, 2),
)
DEFAULT_SEED_PARTITIONS = 4
DEFAULT_INTENTS_PER_PARTITION = 4


@dataclass(frozen=True, slots=True)
class TuningScenarioResult:
    """One deterministic shared-write tuning outcome."""

    partition_count: int
    batch_limit: int
    round_count: int
    processed_total: int
    peak_pending_total: int
    mean_processed_per_round: float


@dataclass(slots=True)
class _InMemorySharedIntentStore:
    """In-memory store for deterministic shared-followup simulation."""

    rows: list[SharedProjectionIntentRow]
    completed_ids: set[str] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        """Initialize the completed intent id set."""

        self.completed_ids = set()

    def claim_partition_lease(self, **_kwargs: object) -> bool:
        """Always grant the simulated partition lease."""

        return True

    def release_partition_lease(self, **_kwargs: object) -> None:
        """Release a simulated partition lease without side effects."""

        return None

    def list_pending_domain_intents(
        self,
        *,
        projection_domain: str,
        limit: int = 100,
    ) -> list[SharedProjectionIntentRow]:
        """Return pending intents for one projection domain."""

        return [
            row
            for row in self.rows
            if row.projection_domain == projection_domain
            and row.completed_at is None
            and row.intent_id not in self.completed_ids
        ][:limit]

    def mark_intents_completed(self, *, intent_ids: list[str]) -> None:
        """Mark one intent id batch completed in the simulated store."""

        completed = set(intent_ids)
        self.completed_ids.update(completed)
        self.rows = [
            (
                replace(row, completed_at=_utc_now(minute=59))
                if row.intent_id in completed
                else row
            )
            for row in self.rows
        ]

    def count_pending_repository_generation_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        generation_id: str,
        projection_domain: str,
    ) -> int:
        """Count pending intents for one repository generation and domain."""

        return sum(
            1
            for row in self.rows
            if row.intent_id not in self.completed_ids
            and row.completed_at is None
            and row.repository_id == repository_id
            and row.source_run_id == source_run_id
            and row.generation_id == generation_id
            and row.projection_domain == projection_domain
        )

    def list_pending_backlog_snapshot(self) -> list[SharedProjectionBacklogSnapshotRow]:
        """Return pending backlog grouped by projection domain."""

        pending_by_domain: dict[str, int] = {}
        oldest_by_domain: dict[str, float] = {}
        now = _utc_now(minute=10)
        for row in self.rows:
            if row.completed_at is not None or row.intent_id in self.completed_ids:
                continue
            pending_by_domain[row.projection_domain] = (
                pending_by_domain.get(row.projection_domain, 0) + 1
            )
            age_seconds = max((now - row.created_at).total_seconds(), 0.0)
            oldest_by_domain[row.projection_domain] = max(
                oldest_by_domain.get(row.projection_domain, 0.0),
                age_seconds,
            )
        return [
            SharedProjectionBacklogSnapshotRow(
                projection_domain=projection_domain,
                pending_depth=pending_depth,
                oldest_age_seconds=oldest_by_domain.get(projection_domain, 0.0),
            )
            for projection_domain, pending_depth in sorted(pending_by_domain.items())
        ]


@dataclass(slots=True)
class _SharedProjectionQueue:
    """Queue stub exposing accepted generations for deterministic simulation."""

    shared_store: _InMemorySharedIntentStore
    accepted_generations: dict[tuple[str, str], str] = field(
        init=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """Derive accepted generations from the seeded intent rows."""

        self.accepted_generations = {
            (row.repository_id, row.source_run_id): row.generation_id
            for row in self.shared_store.rows
        }

    def list_shared_projection_acceptances(
        self,
        *,
        projection_domain: str,
        repository_ids: list[str] | None = None,
    ) -> dict[tuple[str, str], str]:
        """Return accepted generations filtered to the requested repositories."""

        del projection_domain
        if repository_ids is None:
            return dict(self.accepted_generations)
        repository_set = set(repository_ids)
        return {
            key: value
            for key, value in self.accepted_generations.items()
            if key[0] in repository_set
        }

    def complete_shared_projection_domain_by_generation(
        self, **_kwargs: object
    ) -> None:
        """Acknowledge domain completion without mutating simulated state."""

        return None


class _CollectingSession:
    """Minimal session that records simulated graph writes."""

    def __init__(self) -> None:
        """Initialize the recorded call list."""

        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, object]]:
        """Record one simulated Cypher invocation and return no rows."""

        self.calls.append((query, params))
        return []


def _utc_now(*, minute: int = 0, second: int = 0) -> datetime:
    """Return one stable UTC timestamp for deterministic report generation."""

    return datetime(2026, 4, 10, 12, minute, second, tzinfo=timezone.utc)


def _repository_id(candidate_id: int) -> str:
    """Return one stable repository identifier for seeded intents."""

    return f"repository:r_{candidate_id % 3}"


def _workload_id(repository_id: str) -> str:
    """Return the workload identifier paired with one repository id."""

    return f"workload:{repository_id.split(':')[-1]}"


def projection_domains_for_report(*, include_platform: bool) -> list[str]:
    """Return the ordered projection domains for the tuning report."""

    domains = [
        REPO_DEPENDENCY_PROJECTION_DOMAIN,
        WORKLOAD_DEPENDENCY_PROJECTION_DOMAIN,
    ]
    if include_platform:
        return [PLATFORM_INFRA_PROJECTION_DOMAIN, *domains]
    return domains


def _build_balanced_intents(
    *,
    projection_domain: str,
    partition_count: int,
    intents_per_partition: int,
    source_run_id: str,
    generation_id: str,
) -> list[SharedProjectionIntentRow]:
    """Return seeded intents balanced across stable partitions."""

    rows: list[SharedProjectionIntentRow] = []
    candidate_id = 0
    for target_partition in range(partition_count):
        generated = 0
        while generated < intents_per_partition:
            repository_id = _repository_id(candidate_id)
            target_label = f"{projection_domain}-{target_partition}-{candidate_id}"
            if projection_domain == PLATFORM_INFRA_PROJECTION_DOMAIN:
                target_id = f"platform:{target_label}"
                partition_key = f"platform:{repository_id}->{target_id}"
                payload = {
                    "action": "upsert",
                    "repo_id": repository_id,
                    "platform_id": target_id,
                    "platform_name": f"cluster-{target_id}",
                    "platform_kind": "kubernetes_cluster",
                    "platform_provider": "aws",
                    "platform_environment": "qa",
                    "platform_region": "us-east-1",
                    "platform_locator": (
                        "arn:aws:eks:us-east-1:123456789012:cluster/" f"{target_id}"
                    ),
                }
            elif projection_domain == REPO_DEPENDENCY_PROJECTION_DOMAIN:
                target_id = f"repository:{target_label}"
                partition_key = f"repo:{repository_id}->{target_id}"
                payload = {
                    "action": "upsert",
                    "dependency_name": target_id.split(":")[-1],
                    "repo_id": repository_id,
                    "target_repo_id": target_id,
                }
            else:
                target_id = f"workload:{target_label}"
                partition_key = f"workload:{_workload_id(repository_id)}->{target_id}"
                payload = {
                    "action": "upsert",
                    "dependency_name": target_id.split(":")[-1],
                    "repo_id": repository_id,
                    "workload_id": _workload_id(repository_id),
                    "target_workload_id": target_id,
                }
            if (
                partition_for_key(partition_key, partition_count=partition_count)
                != target_partition
            ):
                candidate_id += 1
                continue
            rows.append(
                build_shared_projection_intent(
                    projection_domain=projection_domain,
                    partition_key=partition_key,
                    repository_id=repository_id,
                    source_run_id=source_run_id,
                    generation_id=generation_id,
                    payload=payload,
                    created_at=_utc_now(minute=generated, second=target_partition),
                )
            )
            generated += 1
            candidate_id += 1
    return rows


def _drain_until_empty(
    *,
    shared_projection_intent_store: _InMemorySharedIntentStore,
    fact_work_queue: _SharedProjectionQueue,
    projection_domains: list[str],
    partition_count: int,
    batch_limit: int,
    max_rounds: int = 20,
) -> int:
    """Return the round count required to drain the seeded backlog."""

    for round_number in range(1, max_rounds + 1):
        processed_total = 0
        session = _CollectingSession()
        for projection_domain in projection_domains:
            for partition_id in range(partition_count):
                if projection_domain == PLATFORM_INFRA_PROJECTION_DOMAIN:
                    metrics = process_platform_partition_once(
                        session,
                        shared_projection_intent_store=shared_projection_intent_store,
                        fact_work_queue=fact_work_queue,
                        partition_id=partition_id,
                        partition_count=partition_count,
                        lease_owner=f"worker-{partition_id}",
                        lease_ttl_seconds=60,
                        batch_limit=batch_limit,
                    )
                else:
                    metrics = process_dependency_partition_once(
                        session,
                        shared_projection_intent_store=shared_projection_intent_store,
                        fact_work_queue=fact_work_queue,
                        projection_domain=projection_domain,
                        partition_id=partition_id,
                        partition_count=partition_count,
                        lease_owner=f"worker-{partition_id}",
                        lease_ttl_seconds=60,
                        batch_limit=batch_limit,
                    )
                processed_total += int(metrics.get("processed_intents", 0))
        if not shared_projection_intent_store.list_pending_backlog_snapshot():
            return round_number
        if processed_total <= 0:
            raise ValueError("shared projection drain stalled before convergence")
    raise ValueError("shared projection backlog did not drain within max_rounds")


def _sweep_tuning_candidates(
    *,
    rows: list[SharedProjectionIntentRow],
    projection_domains: list[str],
    candidates: list[tuple[int, int]],
) -> list[TuningScenarioResult]:
    """Return deterministic outcomes for one candidate setting list."""

    results: list[TuningScenarioResult] = []
    initial_pending_total = len(rows)
    for partition_count, batch_limit in candidates:
        store = _InMemorySharedIntentStore(list(rows))
        queue = _SharedProjectionQueue(store)
        round_count = _drain_until_empty(
            shared_projection_intent_store=store,
            fact_work_queue=queue,
            projection_domains=projection_domains,
            partition_count=partition_count,
            batch_limit=batch_limit,
        )
        processed_total = len(rows)
        results.append(
            TuningScenarioResult(
                partition_count=partition_count,
                batch_limit=batch_limit,
                round_count=round_count,
                processed_total=processed_total,
                peak_pending_total=initial_pending_total,
                mean_processed_per_round=processed_total / round_count,
            )
        )
    return results


def _select_preferred_scenario(
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


def build_tuning_report(
    *,
    include_platform: bool = False,
    candidates: list[tuple[int, int]] | None = None,
    seed_partitions: int = DEFAULT_SEED_PARTITIONS,
    intents_per_partition: int = DEFAULT_INTENTS_PER_PARTITION,
) -> dict[str, object]:
    """Return one deterministic shared-write tuning report payload."""

    projection_domains = projection_domains_for_report(
        include_platform=include_platform
    )
    rows: list[SharedProjectionIntentRow] = []
    for projection_domain in projection_domains:
        rows.extend(
            _build_balanced_intents(
                projection_domain=projection_domain,
                partition_count=seed_partitions,
                intents_per_partition=intents_per_partition,
                source_run_id="run-tuning-report",
                generation_id="snapshot-abc",
            )
        )
    scenarios = _sweep_tuning_candidates(
        rows=rows,
        projection_domains=projection_domains,
        candidates=list(candidates or DEFAULT_CANDIDATES),
    )
    recommended = _select_preferred_scenario(scenarios)
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
            for scenario in scenarios
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

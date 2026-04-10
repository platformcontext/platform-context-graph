"""Shared-projection integration harness for deterministic drain validation."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Callable

from platform_context_graph.query.status_shared_projection import (
    enrich_shared_projection_status,
)
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
    process_dependency_partition_once,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    process_platform_partition_once,
)


def _utc_now(*, minute: int = 0, second: int = 0) -> datetime:
    """Return a stable UTC timestamp for shared-projection load tests."""

    return datetime(2026, 4, 10, 12, minute, second, tzinfo=timezone.utc)


def _repository_id(candidate_id: int) -> str:
    """Return one stable repository identifier for seeded intents."""

    return f"repository:r_{candidate_id % 3}"


def _workload_id(repository_id: str) -> str:
    """Return the canonical workload id paired with one repository id."""

    return f"workload:{repository_id.split(':')[-1]}"


def _platform_payload(
    *,
    repository_id: str,
    target_id: str,
) -> dict[str, object]:
    """Return one platform projection payload."""

    return {
        "action": "upsert",
        "repo_id": repository_id,
        "platform_id": target_id,
        "platform_name": f"cluster-{target_id}",
        "platform_kind": "kubernetes_cluster",
        "platform_provider": "aws",
        "platform_environment": "qa",
        "platform_region": "us-east-1",
        "platform_locator": f"arn:aws:eks:us-east-1:123456789012:cluster/{target_id}",
    }


def _repo_dependency_payload(
    *,
    repository_id: str,
    target_id: str,
) -> dict[str, object]:
    """Return one repository dependency payload."""

    return {
        "action": "upsert",
        "dependency_name": target_id.split(":")[-1],
        "repo_id": repository_id,
        "target_repo_id": target_id,
    }


def _workload_dependency_payload(
    *,
    repository_id: str,
    target_id: str,
) -> dict[str, object]:
    """Return one workload dependency payload."""

    return {
        "action": "upsert",
        "dependency_name": target_id.split(":")[-1],
        "repo_id": repository_id,
        "workload_id": _workload_id(repository_id),
        "target_workload_id": target_id,
    }


def _intent_for_domain(
    *,
    projection_domain: str,
    partition_key: str,
    repository_id: str,
    target_id: str,
    source_run_id: str,
    generation_id: str,
    minute: int,
    second: int,
) -> SharedProjectionIntentRow:
    """Return one seeded shared intent for the requested projection domain."""

    if projection_domain == PLATFORM_INFRA_PROJECTION_DOMAIN:
        payload = _platform_payload(repository_id=repository_id, target_id=target_id)
    elif projection_domain == "repo_dependency":
        payload = _repo_dependency_payload(
            repository_id=repository_id, target_id=target_id
        )
    elif projection_domain == "workload_dependency":
        payload = _workload_dependency_payload(
            repository_id=repository_id,
            target_id=target_id,
        )
    else:
        raise ValueError(f"unsupported projection domain: {projection_domain}")

    return build_shared_projection_intent(
        projection_domain=projection_domain,
        partition_key=partition_key,
        repository_id=repository_id,
        source_run_id=source_run_id,
        generation_id=generation_id,
        payload=payload,
        created_at=_utc_now(minute=minute, second=second),
    )


def build_balanced_intents(
    *,
    projection_domain: str,
    partition_count: int,
    intents_per_partition: int,
    source_run_id: str,
    generation_id: str = "snapshot-abc",
) -> list[SharedProjectionIntentRow]:
    """Return seeded intents balanced evenly across stable partitions."""

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
            elif projection_domain == "repo_dependency":
                target_id = f"repository:{target_label}"
                partition_key = f"repo:{repository_id}->{target_id}"
            else:
                target_id = f"workload:{target_label}"
                partition_key = f"workload:{_workload_id(repository_id)}->{target_id}"
            if (
                partition_for_key(partition_key, partition_count=partition_count)
                != target_partition
            ):
                candidate_id += 1
                continue
            rows.append(
                _intent_for_domain(
                    projection_domain=projection_domain,
                    partition_key=partition_key,
                    repository_id=repository_id,
                    target_id=target_id,
                    source_run_id=source_run_id,
                    generation_id=generation_id,
                    minute=generated,
                    second=target_partition,
                )
            )
            generated += 1
            candidate_id += 1
    return rows


@dataclass(slots=True)
class InMemorySharedIntentStore:
    """In-memory store that mimics the shared intent runtime contract."""

    rows: list[SharedProjectionIntentRow]
    enabled: bool = True
    completed_ids: set[str] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        self.completed_ids = set()

    def claim_partition_lease(self, **_kwargs: object) -> bool:
        return True

    def release_partition_lease(self, **_kwargs: object) -> None:
        return None

    def list_pending_domain_intents(
        self,
        *,
        projection_domain: str,
        limit: int = 100,
    ) -> list[SharedProjectionIntentRow]:
        return [
            row
            for row in self.rows
            if row.projection_domain == projection_domain
            and row.completed_at is None
            and row.intent_id not in self.completed_ids
        ][:limit]

    def mark_intents_completed(self, *, intent_ids: list[str]) -> None:
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
        return sum(
            1
            for row in self.rows
            if row.intent_id not in self.completed_ids
            and row.repository_id == repository_id
            and row.source_run_id == source_run_id
            and row.generation_id == generation_id
            and row.projection_domain == projection_domain
            and row.completed_at is None
        )

    def list_pending_backlog_snapshot(
        self,
        *,
        source_run_id: str | None = None,
    ) -> list[SharedProjectionBacklogSnapshotRow]:
        pending_by_domain: dict[str, int] = {}
        oldest_by_domain: dict[str, float] = {}
        now = _utc_now(minute=10)
        for row in self.rows:
            if row.completed_at is not None or row.intent_id in self.completed_ids:
                continue
            if source_run_id and row.source_run_id != source_run_id:
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

    def count_pending_repositories(self, *, source_run_id: str | None) -> int:
        """Return distinct repositories still carrying pending shared work."""

        return len(
            {
                row.repository_id
                for row in self.rows
                if row.intent_id not in self.completed_ids
                and row.completed_at is None
                and (source_run_id is None or row.source_run_id == source_run_id)
            }
        )


@dataclass(slots=True)
class SharedProjectionQueue:
    """Queue stub that exposes acceptance and backlog helpers."""

    shared_store: InMemorySharedIntentStore
    enabled: bool = True
    accepted_generations: dict[tuple[str, str], str] = field(
        init=False,
        default_factory=dict,
    )
    domain_completion_calls: list[dict[str, object]] = field(
        init=False,
        default_factory=list,
    )

    def __post_init__(self) -> None:
        self.accepted_generations = {
            (row.repository_id, row.source_run_id): row.generation_id
            for row in self.shared_store.rows
        }
        self.domain_completion_calls = []

    def list_shared_projection_acceptances(
        self,
        *,
        projection_domain: str,
        repository_ids: list[str] | None = None,
    ) -> dict[tuple[str, str], str]:
        del projection_domain
        if repository_ids is None:
            return dict(self.accepted_generations)
        repository_set = set(repository_ids)
        return {
            key: value
            for key, value in self.accepted_generations.items()
            if key[0] in repository_set
        }

    def complete_shared_projection_domain_by_generation(self, **kwargs: object) -> None:
        self.domain_completion_calls.append(dict(kwargs))

    def count_shared_projection_pending(self, *, source_run_id: str) -> int:
        return self.shared_store.count_pending_repositories(source_run_id=source_run_id)

    def list_shared_projection_backlog_snapshot(
        self,
    ) -> list[SharedProjectionBacklogSnapshotRow]:
        return self.shared_store.list_pending_backlog_snapshot()

    def list_queue_snapshot(self) -> list[object]:
        return []

    def refresh_pool_metrics(self, *, component: str) -> None:
        del component


@dataclass(frozen=True, slots=True)
class DrainRoundSnapshot:
    """One deterministic drain-round summary."""

    round_number: int
    processed_by_domain: dict[str, int]
    pending_by_domain: dict[str, int]
    pending_total: int
    processed_total: int
    status_payload: dict[str, object]


class _CollectingSession:
    """Minimal session that records queries during drain validation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, object]]:
        self.calls.append((query, params))
        return []


def _pending_depths_by_domain(
    shared_projection_intent_store: InMemorySharedIntentStore,
) -> dict[str, int]:
    """Return current pending depth grouped by projection domain."""

    return {
        row.projection_domain: row.pending_depth
        for row in shared_projection_intent_store.list_pending_backlog_snapshot()
    }


def _drain_round(
    *,
    shared_projection_intent_store: InMemorySharedIntentStore,
    fact_work_queue: SharedProjectionQueue,
    projection_domains: list[str],
    partition_count: int,
    batch_limit: int,
    round_number: int,
    sampler: Callable[[], None] | None,
    status_payload: dict[str, object] | None,
) -> DrainRoundSnapshot:
    """Process one deterministic shared-followup round across all partitions."""

    session = _CollectingSession()
    processed_by_domain: dict[str, int] = {}
    for projection_domain in projection_domains:
        processed_by_domain[projection_domain] = 0
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
            processed_by_domain[projection_domain] += int(
                metrics.get("processed_intents", 0)
            )
    if sampler is not None:
        sampler()
    pending_by_domain = _pending_depths_by_domain(shared_projection_intent_store)
    normalized_status = (
        enrich_shared_projection_status(
            dict(status_payload),
            queue=fact_work_queue,
            shared_projection_intent_store=shared_projection_intent_store,
        )
        if status_payload is not None
        else {}
    )
    return DrainRoundSnapshot(
        round_number=round_number,
        processed_by_domain=processed_by_domain,
        pending_by_domain=pending_by_domain,
        pending_total=sum(pending_by_domain.values()),
        processed_total=sum(processed_by_domain.values()),
        status_payload=normalized_status,
    )


def drain_until_empty(
    *,
    shared_projection_intent_store: InMemorySharedIntentStore,
    fact_work_queue: SharedProjectionQueue,
    projection_domains: list[str],
    partition_count: int,
    batch_limit: int,
    sampler: Callable[[], None] | None = None,
    status_payload: dict[str, object] | None = None,
    max_rounds: int = 20,
) -> list[DrainRoundSnapshot]:
    """Drain shared backlog across repeated deterministic rounds."""

    rounds: list[DrainRoundSnapshot] = []
    for round_number in range(1, max_rounds + 1):
        snapshot = _drain_round(
            shared_projection_intent_store=shared_projection_intent_store,
            fact_work_queue=fact_work_queue,
            projection_domains=projection_domains,
            partition_count=partition_count,
            batch_limit=batch_limit,
            round_number=round_number,
            sampler=sampler,
            status_payload=status_payload,
        )
        rounds.append(snapshot)
        if snapshot.pending_total == 0:
            return rounds
        if snapshot.processed_total <= 0:
            raise AssertionError("shared projection drain stalled before convergence")
    raise AssertionError("shared projection backlog did not drain within max_rounds")

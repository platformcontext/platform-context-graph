"""Tests for stable shared-projection partitioning."""

from __future__ import annotations

from platform_context_graph.resolution.shared_projection.models import (
    build_shared_projection_intent,
)


def test_partition_for_key_is_stable_for_same_platform_id() -> None:
    """The same platform partition key should always map to the same partition."""

    from platform_context_graph.resolution.shared_projection.partitioning import (
        partition_for_key,
    )

    partition = partition_for_key("platform:kubernetes:qa", partition_count=8)

    assert partition == partition_for_key(
        "platform:kubernetes:qa",
        partition_count=8,
    )


def test_rows_for_partition_keeps_same_platform_in_one_partition() -> None:
    """Rows sharing one platform id should only appear in one worker partition."""

    from datetime import datetime
    from datetime import timezone

    from platform_context_graph.resolution.shared_projection.partitioning import (
        partition_for_key,
    )
    from platform_context_graph.resolution.shared_projection.partitioning import (
        rows_for_partition,
    )

    rows = [
        build_shared_projection_intent(
            projection_domain="platform_infra",
            partition_key="platform:kubernetes:qa",
            repository_id="repository:r_payments",
            source_run_id="run-123",
            generation_id="gen-a",
            payload={"platform_id": "platform:kubernetes:qa", "action": "upsert"},
            created_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
        ),
        build_shared_projection_intent(
            projection_domain="platform_infra",
            partition_key="platform:kubernetes:qa",
            repository_id="repository:r_billing",
            source_run_id="run-123",
            generation_id="gen-b",
            payload={"platform_id": "platform:kubernetes:qa", "action": "upsert"},
            created_at=datetime(2026, 4, 9, 12, 1, tzinfo=timezone.utc),
        ),
    ]

    partition_id = partition_for_key("platform:kubernetes:qa", partition_count=8)

    assert (
        len(rows_for_partition(rows, partition_id=partition_id, partition_count=8)) == 2
    )
    for other_partition in range(8):
        if other_partition == partition_id:
            continue
        assert (
            rows_for_partition(
                rows,
                partition_id=other_partition,
                partition_count=8,
            )
            == []
        )


def test_partition_for_key_allows_different_platforms_to_progress_independently() -> (
    None
):
    """Different platform ids should not all collapse into one partition."""

    from platform_context_graph.resolution.shared_projection.partitioning import (
        partition_for_key,
    )

    partitions = {
        partition_for_key(f"platform:kubernetes:qa-{index}", partition_count=8)
        for index in range(12)
    }

    assert len(partitions) > 1

"""Tests for workload shared-projection metric merging helpers."""

from __future__ import annotations

from platform_context_graph.resolution.workloads.metrics import (
    merge_shared_projection_payload,
)


def test_merge_shared_projection_payload_ignores_none_generation_ids() -> None:
    """Missing accepted generation ids should not become the string ``None``."""

    totals: dict[str, object] = {}

    merge_shared_projection_payload(
        totals,
        {
            "shared_projection": {
                "accepted_generation_id": None,
                "authoritative_domains": ["repo_dependency"],
                "intent_count": 1,
            }
        },
    )
    merge_shared_projection_payload(
        totals,
        {
            "shared_projection": {
                "accepted_generation_id": "gen-123",
                "authoritative_domains": ["workload_dependency"],
                "intent_count": 2,
            }
        },
    )

    assert totals["shared_projection"] == {
        "accepted_generation_id": "gen-123",
        "authoritative_domains": [
            "repo_dependency",
            "workload_dependency",
        ],
        "intent_count": 3,
    }

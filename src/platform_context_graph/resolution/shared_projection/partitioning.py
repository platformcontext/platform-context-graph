"""Stable partitioning helpers for shared projection domains."""

from __future__ import annotations

import hashlib

from .models import SharedProjectionIntentRow


def partition_for_key(partition_key: str, *, partition_count: int) -> int:
    """Return the stable partition id for one shared projection key."""

    if partition_count <= 0:
        raise ValueError("partition_count must be positive")
    digest = hashlib.sha256(partition_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False) % partition_count


def rows_for_partition(
    rows: list[SharedProjectionIntentRow],
    *,
    partition_id: int,
    partition_count: int,
) -> list[SharedProjectionIntentRow]:
    """Return intent rows whose partition key belongs to one worker partition."""

    return [
        row
        for row in rows
        if partition_for_key(row.partition_key, partition_count=partition_count)
        == partition_id
    ]

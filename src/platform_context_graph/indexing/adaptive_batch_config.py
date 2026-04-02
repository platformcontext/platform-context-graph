"""Class-aware adaptive batch configuration for indexing.

Returns batch sizing parameters tuned for each repository class.
Gated behind ``PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED``; when disabled,
static medium-class defaults are returned regardless of repo class.

The sizing tables here are the first-pass values derived from the
PRD's directional guidance. They should be refined after A/B comparison
using run summary artifacts from the Observability PRD.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AdaptiveBatchConfig:
    """Batch sizing parameters for a specific repository class.

    Attributes:
        repo_class: The repo class this config was generated for.
        file_batch_size: Files per commit batch (coordinator-level).
        flush_row_threshold: Row count triggering early batch flush.
        entity_batch_size: Neo4j UNWIND chunk size for entity writes.
        tx_file_limit: Files per Neo4j transaction within a batch.
        content_upsert_batch_size: Postgres content upsert batch size.
    """

    repo_class: str
    file_batch_size: int
    flush_row_threshold: int
    entity_batch_size: int
    tx_file_limit: int
    content_upsert_batch_size: int


# Sizing tables: monotonically decreasing from small → dangerous.
# medium = current static defaults for backwards compatibility.
_CLASS_CONFIGS: dict[str, AdaptiveBatchConfig] = {
    "small": AdaptiveBatchConfig(
        repo_class="small",
        file_batch_size=100,
        flush_row_threshold=3000,
        entity_batch_size=10_000,
        tx_file_limit=10,
        content_upsert_batch_size=750,
    ),
    "medium": AdaptiveBatchConfig(
        repo_class="medium",
        file_batch_size=50,
        flush_row_threshold=2000,
        entity_batch_size=10_000,
        tx_file_limit=5,
        content_upsert_batch_size=500,
    ),
    "large": AdaptiveBatchConfig(
        repo_class="large",
        file_batch_size=50,
        flush_row_threshold=1500,
        entity_batch_size=7_500,
        tx_file_limit=5,
        content_upsert_batch_size=350,
    ),
    "xlarge": AdaptiveBatchConfig(
        repo_class="xlarge",
        file_batch_size=35,
        flush_row_threshold=750,
        entity_batch_size=3_500,
        tx_file_limit=4,
        content_upsert_batch_size=150,
    ),
    "dangerous": AdaptiveBatchConfig(
        repo_class="dangerous",
        file_batch_size=10,
        flush_row_threshold=250,
        entity_batch_size=1_000,
        tx_file_limit=1,
        content_upsert_batch_size=50,
    ),
}

_DEFAULT_CLASS = "medium"


def batch_config_for_class(repo_class: str | None) -> AdaptiveBatchConfig:
    """Return batch sizing config for the given repository class.

    Args:
        repo_class: One of ``small``, ``medium``, ``large``, ``xlarge``,
            ``dangerous``, or ``None`` for medium defaults.

    Returns:
        An ``AdaptiveBatchConfig`` with tuned batch sizing parameters.
    """
    if repo_class and repo_class in _CLASS_CONFIGS:
        return _CLASS_CONFIGS[repo_class]
    return _CLASS_CONFIGS[_DEFAULT_CLASS]


def resolve_batch_config(
    *,
    repo_class: str | None = None,
) -> AdaptiveBatchConfig:
    """Return batch config respecting the adaptive batching feature flag.

    When ``PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED`` is ``false`` (default),
    returns static medium defaults regardless of ``repo_class``.

    Args:
        repo_class: The assigned repo class, or ``None``.

    Returns:
        An ``AdaptiveBatchConfig`` instance.
    """
    enabled = (
        os.environ.get("PCG_ADAPTIVE_GRAPH_BATCHING_ENABLED", "false").lower() == "true"
    )
    if not enabled:
        return _CLASS_CONFIGS[_DEFAULT_CLASS]
    return batch_config_for_class(repo_class)


__all__ = [
    "AdaptiveBatchConfig",
    "batch_config_for_class",
    "resolve_batch_config",
]

"""Core orchestration hooks for fact-driven graph projection."""

from __future__ import annotations

from typing import Any

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.resolution.projection import project_git_fact_records
from platform_context_graph.resolution.projection.relationships import (
    project_git_relationship_fact_records,
)


def project_work_item(
    work_item: FactWorkItemRow,
    *,
    builder: Any | None = None,
    fact_store: Any | None = None,
    fact_projector: Any = project_git_fact_records,
    relationship_projector: Any = project_git_relationship_fact_records,
    debug_log_fn: Any = lambda *_args, **_kwargs: None,
    warning_logger_fn: Any = lambda *_args, **_kwargs: None,
) -> dict[str, Any] | None:
    """Project one work item into canonical graph state.

    Args:
        work_item: The claimed work item to process.
    """

    if builder is None or fact_store is None:
        return None

    fact_records: list[FactRecordRow] = fact_store.list_facts(
        repository_id=work_item.repository_id,
        source_run_id=work_item.source_run_id,
    )
    fact_metrics = fact_projector(builder=builder, fact_records=fact_records)
    relationship_metrics = relationship_projector(
        builder=builder,
        fact_records=fact_records,
        debug_log_fn=debug_log_fn,
        warning_logger_fn=warning_logger_fn,
    )
    return {
        "facts": fact_metrics,
        "relationships": relationship_metrics,
    }

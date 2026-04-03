"""Core orchestration hooks for fact-driven graph projection."""

from __future__ import annotations

from platform_context_graph.facts.work_queue.models import FactWorkItemRow


def project_work_item(work_item: FactWorkItemRow) -> None:
    """Project one work item into canonical graph state.

    This Phase 2 shell keeps the runtime importable while later chunks add
    concrete projection handlers.

    Args:
        work_item: The claimed work item to process.
    """

    del work_item

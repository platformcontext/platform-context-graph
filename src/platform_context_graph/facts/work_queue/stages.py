"""Stable processing stage names for fact-projection work items."""

from __future__ import annotations

PROJECT_WORK_ITEM_STAGE = "project_work_item"
LOAD_FACTS_STAGE = "load_facts"
PROJECT_FACTS_STAGE = "project_facts"
PROJECT_ENTITY_BATCHES_STAGE = "project_entity_batches"
PROJECT_RELATIONSHIPS_STAGE = "project_relationships"
PROJECT_WORKLOADS_STAGE = "project_workloads"
PROJECT_PLATFORMS_STAGE = "project_platforms"


class ProjectionStageError(Exception):
    """Wrap one exception with the projection stage that raised it."""

    __slots__ = ("stage", "cause")

    def __init__(self, stage: str, cause: BaseException) -> None:
        """Initialize one stage wrapper around an underlying exception."""

        super().__init__(str(cause))
        self.stage = stage
        self.cause = cause


__all__ = [
    "LOAD_FACTS_STAGE",
    "PROJECT_ENTITY_BATCHES_STAGE",
    "PROJECT_FACTS_STAGE",
    "PROJECT_PLATFORMS_STAGE",
    "PROJECT_RELATIONSHIPS_STAGE",
    "PROJECT_WORK_ITEM_STAGE",
    "PROJECT_WORKLOADS_STAGE",
    "ProjectionStageError",
]

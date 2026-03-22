"""Shared HTTP and MCP request models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .entities import (
    EntityType,
    WorkloadKind,
    normalize_entity_type,
    normalize_workload_kind,
)


class ResolveEntityRequest(BaseModel):
    """Request model for canonical entity resolution."""

    model_config = ConfigDict(extra="forbid")

    query: str
    types: list[EntityType] | None = None
    kinds: list[WorkloadKind] | None = None
    environment: str | None = None
    repo_id: str | None = None
    exact: bool = False
    limit: int = Field(default=10, ge=1)

    @field_validator("types", mode="before")
    @classmethod
    def normalize_types(cls, value: list[EntityType | str] | None) -> list[EntityType] | None:
        """Accept public entity-type aliases while preserving canonical enums."""
        if value is None:
            return None
        return [normalize_entity_type(item) for item in value]

    @field_validator("kinds", mode="before")
    @classmethod
    def normalize_kinds(
        cls, value: list[WorkloadKind | str] | None
    ) -> list[WorkloadKind] | None:
        """Accept public workload-kind spellings while preserving canonical enums."""
        if value is None:
            return None
        return [normalize_workload_kind(item) for item in value]

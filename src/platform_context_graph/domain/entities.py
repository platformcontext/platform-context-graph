"""Canonical entity models shared by the HTTP API and MCP surfaces."""

from __future__ import annotations

import re
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, model_validator

_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*:[^/\s:][^/\s]*(?::[^/\s:][^/\s]*)*$")


def _canonical_prefix(entity_type: EntityType) -> str:
    """Return the canonical identifier prefix for an entity type."""
    return entity_type.value.replace("_", "-")


def _is_canonical_id_for_type(value: str, entity_type: EntityType) -> bool:
    """Validate that an identifier matches the expected canonical entity type."""
    if value.startswith("/") or not _CANONICAL_ID_RE.match(value):
        return False
    prefix, _, _ = value.partition(":")
    return prefix == _canonical_prefix(entity_type)


class EntityType(str, Enum):
    """Supported canonical entity kinds in the PCG graph model."""

    repository = "repository"
    content_entity = "content_entity"
    data_asset = "data_asset"
    data_column = "data_column"
    analytics_model = "analytics_model"
    query_execution = "query_execution"
    dashboard_asset = "dashboard_asset"
    data_quality_check = "data_quality_check"
    file = "file"
    workload = "workload"
    workload_instance = "workload_instance"
    image = "image"
    k8s_resource = "k8s_resource"
    terraform_module = "terraform_module"
    terraform_resource = "terraform_resource"
    cloud_resource = "cloud_resource"
    endpoint = "endpoint"
    environment = "environment"


class WorkloadKind(str, Enum):
    """Supported workload subtypes for deployable compute units."""

    service = "service"
    worker = "worker"
    consumer = "consumer"
    cronjob = "cronjob"
    batch = "batch"
    lambda_ = "lambda"


_ENTITY_TYPE_ALIASES: Mapping[str, str] = {
    # Argo CD resources are currently exposed through the broader Kubernetes
    # resource filter space because the canonical entity model does not yet
    # assign them first-class entity types.
    "argocd_application": EntityType.k8s_resource.value,
    "argocd_applicationset": EntityType.k8s_resource.value,
    "argocd_application_set": EntityType.k8s_resource.value,
}


def normalize_entity_type(value: EntityType | str) -> EntityType:
    """Normalize public entity-type spellings into canonical enum values."""
    if isinstance(value, EntityType):
        return value
    normalized = value.strip().lower().replace("-", "_")
    return EntityType(_ENTITY_TYPE_ALIASES.get(normalized, normalized))


def normalize_workload_kind(value: WorkloadKind | str) -> WorkloadKind:
    """Normalize public workload-kind spellings into canonical enum values."""
    if isinstance(value, WorkloadKind):
        return value
    return WorkloadKind(value.strip().lower().replace("-", "_"))


class EntityRef(BaseModel):
    """Portable reference to an entity returned by PCG APIs.

    Attributes:
        id: Canonical entity identifier.
        type: Canonical entity type.
        kind: Workload subtype when the entity is a workload or workload instance.
        name: Human-readable entity name.
        environment: Environment name for environment-scoped entities.
        workload_id: Canonical workload ID for workload instances.
        path: Legacy or source path metadata when still needed for compatibility.
        relative_path: Portable repo-relative path for file references.
        local_path: Server-local checkout path when known.
        repo_slug: Remote repository slug such as ``org/repo``.
        remote_url: Normalized remote repository URL.
        has_remote: Whether the repository has a known remote.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    type: EntityType
    kind: WorkloadKind | None = None
    name: str
    environment: str | None = None
    workload_id: str | None = None
    path: str | None = None
    relative_path: str | None = None
    local_path: str | None = None
    repo_slug: str | None = None
    remote_url: str | None = None
    has_remote: bool | None = None

    @model_validator(mode="after")
    def validate_canonical_invariants(self) -> "EntityRef":
        """Enforce canonical identifier and workload-shape invariants.

        Returns:
            The validated entity reference.

        Raises:
            ValueError: If the reference shape is inconsistent with its type.
        """
        if not _is_canonical_id_for_type(self.id, self.type):
            raise ValueError("id must be a canonical entity identifier, not a raw path")

        if self.path is not None and self.id == self.path:
            raise ValueError("id must not duplicate the raw path")
        if self.local_path is not None and self.id == self.local_path:
            raise ValueError("id must not duplicate the local path")

        if self.type == EntityType.workload_instance:
            if self.environment is None:
                raise ValueError("environment is required for workload_instance refs")
            if self.workload_id is None:
                raise ValueError("workload_id is required for workload_instance refs")
            if self.kind is None:
                raise ValueError("kind is required for workload_instance refs")
            if not _is_canonical_id_for_type(self.workload_id, EntityType.workload):
                raise ValueError("workload_id must be a canonical workload identifier")
        else:
            if self.workload_id is not None:
                raise ValueError("workload_id is only valid for workload_instance refs")
            if self.kind is not None and self.type not in {
                EntityType.workload,
                EntityType.workload_instance,
            }:
                raise ValueError("kind is only valid for workload refs")
            if self.environment is not None and self.type not in {
                EntityType.environment,
                EntityType.workload_instance,
            }:
                raise ValueError(
                    "environment is only valid for environment and workload_instance refs"
                )

        if self.type == EntityType.workload and self.kind is None:
            raise ValueError("kind is required for workload refs")

        if self.type == EntityType.workload and self.environment is not None:
            raise ValueError("environment is not valid for workload refs")

        return self

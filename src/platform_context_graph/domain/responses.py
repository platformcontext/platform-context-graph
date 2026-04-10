"""Shared HTTP and MCP response models for PlatformContextGraph."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .investigation_responses import InvestigationResponse

from .entities import EntityRef, EntityType


class EvidenceItem(BaseModel):
    """Single evidence fragment supporting an inferred answer."""

    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    detail: str | None = None
    weight: float | None = None


class InferenceMetadata(BaseModel):
    """Inference confidence and evidence attached to a response field."""

    model_config = ConfigDict(extra="forbid")

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class AliasMetadata(BaseModel):
    """Metadata describing alias resolution to a canonical entity type."""

    model_config = ConfigDict(extra="forbid")

    requested_as: str
    canonical_type: EntityType
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = None


class RepoAccess(BaseModel):
    """Structured handoff contract for repository access on remote deployments."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["available", "needs_local_checkout", "unknown"]
    repo_id: str
    repo_slug: str | None = None
    remote_url: str | None = None
    local_path: str | None = None
    recommended_action: Literal[
        "use_local_checkout", "ask_user_for_local_path", "clone_locally"
    ]
    interaction_mode: Literal["elicitation", "conversational"]


class ContentLine(BaseModel):
    """One line in a file-content line range response."""

    model_config = ConfigDict(extra="forbid")

    line_number: int
    content: str


class ContentMetadataFields(BaseModel):
    """Metadata attached to indexed content rows and search matches."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: str | None = None
    template_dialect: str | None = None
    iac_relevant: bool | None = None


class FileContentResponse(ContentMetadataFields):
    """Portable file-content response for HTTP and MCP consumers."""

    model_config = ConfigDict(extra="forbid")

    available: bool = True
    repo_id: str
    relative_path: str
    content: str | None = None
    line_count: int | None = None
    language: str | None = None
    commit_sha: str | None = None
    content_hash: str | None = None
    index_status: str | None = None
    source_backend: Literal["postgres", "workspace", "graph-cache", "unavailable"]
    repo_access: RepoAccess | None = None


class FileLinesResponse(ContentMetadataFields):
    """Portable file line-range response for HTTP and MCP consumers."""

    model_config = ConfigDict(extra="forbid")

    available: bool = True
    repo_id: str
    relative_path: str
    start_line: int
    end_line: int
    lines: list[ContentLine] = Field(default_factory=list)
    index_status: str | None = None
    source_backend: Literal["postgres", "workspace", "graph-cache", "unavailable"]
    repo_access: RepoAccess | None = None


class EntityContentResponse(ContentMetadataFields):
    """Portable entity-content response for HTTP and MCP consumers."""

    model_config = ConfigDict(extra="forbid")

    available: bool = True
    entity_id: str
    repo_id: str | None = None
    relative_path: str | None = None
    entity_type: str | None = None
    entity_name: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    start_byte: int | None = None
    end_byte: int | None = None
    language: str | None = None
    content: str | None = None
    index_status: str | None = None
    source_backend: Literal["postgres", "workspace", "graph-cache", "unavailable"]
    repo_access: RepoAccess | None = None


class IngesterStatusResponse(BaseModel):
    """Runtime ingester status exposed by the API and MCP layers."""

    model_config = ConfigDict(extra="forbid")

    runtime_family: Literal["ingester"] = "ingester"
    ingester: str
    provider: str
    source_mode: str | None = None
    status: str
    active_run_id: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    next_retry_at: str | None = None
    last_error_kind: str | None = None
    last_error_message: str | None = None
    active_repository_path: str | None = None
    active_phase: str | None = None
    active_phase_started_at: str | None = None
    active_current_file: str | None = None
    active_last_progress_at: str | None = None
    active_commit_started_at: str | None = None
    repository_count: int = 0
    pulled_repositories: int = 0
    in_sync_repositories: int = 0
    pending_repositories: int = 0
    completed_repositories: int = 0
    failed_repositories: int = 0
    shared_projection_pending_repositories: int = 0
    shared_projection_backlog: list[SharedProjectionBacklogItem] = Field(
        default_factory=list
    )
    shared_projection_tuning: SharedProjectionTuningStatus | None = None
    scan_request_state: str = "idle"
    scan_request_token: str | None = None
    scan_requested_at: str | None = None
    scan_requested_by: str | None = None
    scan_started_at: str | None = None
    scan_completed_at: str | None = None
    scan_error_message: str | None = None
    updated_at: str | None = None


class SharedProjectionBacklogItem(BaseModel):
    """One shared-follow-up backlog summary entry in ingester status."""

    model_config = ConfigDict(extra="forbid")

    projection_domain: str
    pending_intents: int
    oldest_pending_age_seconds: float


class SharedProjectionTuningRecommendation(BaseModel):
    """One deterministic shared-write tuning recommendation."""

    model_config = ConfigDict(extra="forbid")

    setting: str
    partition_count: int
    batch_limit: int
    round_count: int
    processed_total: int
    peak_pending_total: int
    mean_processed_per_round: float


class SharedProjectionTuningStatus(BaseModel):
    """Status-safe shared-write tuning summary for operators."""

    model_config = ConfigDict(extra="forbid")

    projection_domains: list[str] = Field(default_factory=list)
    include_platform: bool = False
    current_pending_intents: int = 0
    current_oldest_pending_age_seconds: float = 0.0
    recommended: SharedProjectionTuningRecommendation


class IngesterScanRequestResponse(BaseModel):
    """Scan-trigger response exposed by the API and control surfaces."""

    model_config = ConfigDict(extra="forbid")

    runtime_family: Literal["ingester"] = "ingester"
    ingester: str
    provider: str
    accepted: bool
    scan_request_token: str
    scan_request_state: str
    scan_requested_at: str | None = None
    scan_requested_by: str | None = None


class FileContentMatch(ContentMetadataFields):
    """Search match returned for file-content queries."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    relative_path: str
    language: str | None = None
    snippet: str
    source_backend: Literal["postgres", "workspace", "graph-cache", "unavailable"]


class FileContentSearchResponse(BaseModel):
    """Search response for file-content queries."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    matches: list[FileContentMatch] = Field(default_factory=list)
    error: str | None = None


class EntityContentMatch(ContentMetadataFields):
    """Search match returned for entity-content queries."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    repo_id: str
    relative_path: str
    entity_type: str
    entity_name: str
    language: str | None = None
    snippet: str
    source_backend: Literal["postgres", "workspace", "graph-cache", "unavailable"]


class EntityContentSearchResponse(BaseModel):
    """Search response for entity-content queries."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    matches: list[EntityContentMatch] = Field(default_factory=list)
    error: str | None = None


class ResolveEntityMatch(BaseModel):
    """Single ranked entity match returned by entity resolution."""

    model_config = ConfigDict(extra="forbid")

    ref: EntityRef
    score: float
    inference: InferenceMetadata | None = None
    match_type: str | None = None
    alias: AliasMetadata | None = None


class ResolveEntityResponse(BaseModel):
    """Response payload for the entity-resolution API."""

    model_config = ConfigDict(extra="forbid")

    matches: list[ResolveEntityMatch] = Field(default_factory=list)


class ProblemDetails(BaseModel):
    """RFC 7807-style problem details payload."""

    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class WorkloadContextResponse(BaseModel):
    """Context response for a workload or service query."""

    model_config = ConfigDict(extra="forbid")

    workload: EntityRef
    instance: EntityRef | None = None
    instances: list[EntityRef] = Field(default_factory=list)
    repositories: list[EntityRef] = Field(default_factory=list)
    images: list[EntityRef] = Field(default_factory=list)
    k8s_resources: list[EntityRef] = Field(default_factory=list)
    cloud_resources: list[EntityRef] = Field(default_factory=list)
    shared_resources: list[EntityRef] = Field(default_factory=list)
    dependencies: list[EntityRef] = Field(default_factory=list)
    entrypoints: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    requested_as: Literal["service"] | None = None


class StorySection(BaseModel):
    """One named story section in a higher-level narrative response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    summary: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class StoryResponse(BaseModel):
    """Structured story response shared by MCP and HTTP story surfaces."""

    model_config = ConfigDict(extra="forbid")

    subject: EntityRef
    story: list[str] = Field(default_factory=list)
    story_sections: list[StorySection] = Field(default_factory=list)
    deployment_overview: dict[str, Any] | None = None
    gitops_overview: dict[str, Any] | None = None
    documentation_overview: dict[str, Any] | None = None
    support_overview: dict[str, Any] | None = None
    controller_overview: dict[str, Any] | None = None
    runtime_overview: dict[str, Any] | None = None
    deployment_facts: list[dict[str, Any]] = Field(default_factory=list)
    deployment_fact_summary: dict[str, Any] | None = None
    code_overview: dict[str, Any] | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    coverage: dict[str, Any] | None = None
    drilldowns: dict[str, Any] = Field(default_factory=dict)
    requested_as: Literal["service"] | None = None


class EntityContextResponse(BaseModel):
    """Generic context response for any canonical entity type."""

    model_config = ConfigDict(extra="allow")

    entity: EntityRef
    related: list[dict[str, Any]] = Field(default_factory=list)
    workload: EntityRef | None = None
    instance: EntityRef | None = None
    instances: list[EntityRef] = Field(default_factory=list)
    repositories: list[EntityRef] = Field(default_factory=list)
    images: list[EntityRef] = Field(default_factory=list)
    k8s_resources: list[EntityRef] = Field(default_factory=list)
    cloud_resources: list[EntityRef] = Field(default_factory=list)
    shared_resources: list[EntityRef] = Field(default_factory=list)
    dependencies: list[EntityRef] = Field(default_factory=list)
    entrypoints: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    requested_as: Literal["service"] | None = None


T = TypeVar("T")


class ResponseEnvelope(BaseModel, Generic[T]):
    """Envelope carrying either successful data or a problem response."""

    model_config = ConfigDict(extra="forbid")

    data: T | None = None
    problem: ProblemDetails | None = None

    @model_validator(mode="after")
    def validate_one_of(self) -> "ResponseEnvelope[T]":
        """Ensure that exactly one response branch is populated.

        Returns:
            The validated response envelope.

        Raises:
            ValueError: If both ``data`` and ``problem`` are present or absent.
        """
        has_data = self.data is not None
        has_problem = self.problem is not None
        if has_data == has_problem:
            raise ValueError(
                "ResponseEnvelope must contain exactly one of data or problem"
            )
        return self

"""Structured response models for investigation-oriented query surfaces."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .framework_responses import FrameworkSummary

InvestigationIntent = Literal[
    "deployment",
    "network",
    "dependencies",
    "support",
    "overview",
]
InvestigationCoverageState = Literal["complete", "partial", "unknown"]
InvestigationDeploymentMode = Literal["single_plane", "multi_plane", "sparse", "none"]


class InvestigationRepositoryEvidence(BaseModel):
    """One repository considered during a service investigation."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str | None = None
    repo_name: str
    reason: str
    evidence_families: list[str] = Field(default_factory=list)


class InvestigationDeploymentPlane(BaseModel):
    """One deployment plane detected during the investigation."""

    model_config = ConfigDict(extra="forbid")

    name: str
    evidence_families: list[str] = Field(default_factory=list)


class InvestigationCoverageSummary(BaseModel):
    """Coverage accounting for one investigation result."""

    model_config = ConfigDict(extra="forbid")

    searched_repository_count: int = 0
    repositories_with_evidence_count: int = 0
    searched_evidence_families: list[str] = Field(default_factory=list)
    found_evidence_families: list[str] = Field(default_factory=list)
    missing_evidence_families: list[str] = Field(default_factory=list)
    deployment_mode: InvestigationDeploymentMode = "none"
    deployment_planes: list[InvestigationDeploymentPlane] = Field(default_factory=list)
    graph_completeness: InvestigationCoverageState = "unknown"
    content_completeness: InvestigationCoverageState = "unknown"


class InvestigationFinding(BaseModel):
    """One human-readable finding emitted by the orchestrator."""

    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    evidence_families: list[str] = Field(default_factory=list)


class InvestigationNextCall(BaseModel):
    """One suggested follow-up PCG call."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    reason: str
    args: dict[str, str | int | bool] = Field(default_factory=dict)


class InvestigationResponse(BaseModel):
    """Top-level response for a service investigation request."""

    model_config = ConfigDict(extra="forbid")

    summary: list[str] = Field(default_factory=list)
    framework_summary: FrameworkSummary | None = None
    repositories_considered: list[InvestigationRepositoryEvidence] = Field(
        default_factory=list
    )
    repositories_with_evidence: list[InvestigationRepositoryEvidence] = Field(
        default_factory=list
    )
    evidence_families_found: list[str] = Field(default_factory=list)
    coverage_summary: InvestigationCoverageSummary
    investigation_findings: list[InvestigationFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    recommended_next_calls: list[InvestigationNextCall] = Field(default_factory=list)

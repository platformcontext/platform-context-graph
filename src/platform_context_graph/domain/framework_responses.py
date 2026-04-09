"""Typed framework-summary response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReactBoundary = Literal["client", "server", "shared"]
NextModuleKind = Literal["page", "layout", "route"]
NextMetadataExports = Literal["static", "dynamic", "both", "none"]


class FrameworkSampleModule(BaseModel):
    """One bounded sample module used in framework summaries."""

    model_config = ConfigDict(extra="forbid")

    relative_path: str
    boundary: ReactBoundary | None = None
    component_exports: list[str] = Field(default_factory=list)
    hooks_used: list[str] = Field(default_factory=list)
    module_kind: NextModuleKind | None = None
    route_verbs: list[str] = Field(default_factory=list)
    route_methods: list[str] = Field(default_factory=list)
    route_paths: list[str] = Field(default_factory=list)
    server_symbols: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    client_symbols: list[str] = Field(default_factory=list)
    metadata_exports: NextMetadataExports | None = None
    route_segments: list[str] = Field(default_factory=list)
    runtime_boundary: ReactBoundary | None = None


class ReactFrameworkSummary(BaseModel):
    """Bounded React file summary for one repository."""

    model_config = ConfigDict(extra="forbid")

    module_count: int = 0
    client_boundary_count: int = 0
    server_boundary_count: int = 0
    shared_boundary_count: int = 0
    component_module_count: int = 0
    hook_module_count: int = 0
    sample_modules: list[FrameworkSampleModule] = Field(default_factory=list)


class NextJsFrameworkSummary(BaseModel):
    """Bounded Next.js file summary for one repository."""

    model_config = ConfigDict(extra="forbid")

    module_count: int = 0
    page_count: int = 0
    layout_count: int = 0
    route_count: int = 0
    metadata_module_count: int = 0
    route_handler_module_count: int = 0
    client_runtime_count: int = 0
    server_runtime_count: int = 0
    route_verbs: list[str] = Field(default_factory=list)
    sample_modules: list[FrameworkSampleModule] = Field(default_factory=list)


class NodeHttpFrameworkSummary(BaseModel):
    """Bounded route-framework summary for one repository."""

    model_config = ConfigDict(extra="forbid")

    module_count: int = 0
    route_path_count: int = 0
    route_methods: list[str] = Field(default_factory=list)
    sample_modules: list[FrameworkSampleModule] = Field(default_factory=list)


class ProviderFrameworkSummary(BaseModel):
    """Bounded provider SDK summary for one repository."""

    model_config = ConfigDict(extra="forbid")

    module_count: int = 0
    services: list[str] = Field(default_factory=list)
    client_symbols: list[str] = Field(default_factory=list)
    sample_modules: list[FrameworkSampleModule] = Field(default_factory=list)


class FrameworkSummary(BaseModel):
    """Top-level framework summary for one repository-like subject."""

    model_config = ConfigDict(extra="forbid")

    frameworks: list[str] = Field(default_factory=list)
    react: ReactFrameworkSummary | None = None
    nextjs: NextJsFrameworkSummary | None = None
    express: NodeHttpFrameworkSummary | None = None
    hapi: NodeHttpFrameworkSummary | None = None
    fastapi: NodeHttpFrameworkSummary | None = None
    flask: NodeHttpFrameworkSummary | None = None
    aws: ProviderFrameworkSummary | None = None
    gcp: ProviderFrameworkSummary | None = None

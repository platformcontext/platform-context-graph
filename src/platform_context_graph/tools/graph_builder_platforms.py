"""Compatibility facade for workload platform materialization helpers."""

from ..resolution.platforms import canonical_platform_id
from ..resolution.platforms import extract_terraform_platform_name
from ..resolution.platforms import infer_gitops_platform_id
from ..resolution.platforms import infer_gitops_platform_kind
from ..resolution.platforms import infer_infrastructure_platform_descriptor
from ..resolution.platforms import infer_runtime_platform_kind
from ..resolution.platforms import infer_terraform_platform_kind
from ..resolution.platforms import materialize_infrastructure_platforms
from ..resolution.platforms import materialize_infrastructure_platforms_for_repo_paths
from ..resolution.platforms import materialize_runtime_platform

__all__ = [
    "canonical_platform_id",
    "extract_terraform_platform_name",
    "infer_gitops_platform_id",
    "infer_gitops_platform_kind",
    "infer_infrastructure_platform_descriptor",
    "infer_runtime_platform_kind",
    "infer_terraform_platform_kind",
    "materialize_infrastructure_platforms",
    "materialize_infrastructure_platforms_for_repo_paths",
    "materialize_runtime_platform",
]

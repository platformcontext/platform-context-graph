"""Compatibility facade for runtime platform family helpers."""

from ..resolution.platform_families import TerraformRuntimeFamily
from ..resolution.platform_families import format_platform_kind_label
from ..resolution.platform_families import infer_infrastructure_runtime_family_kind
from ..resolution.platform_families import infer_runtime_family_kind_from_identifiers
from ..resolution.platform_families import infer_terraform_runtime_family_kind
from ..resolution.platform_families import iter_runtime_families
from ..resolution.platform_families import lookup_runtime_family
from ..resolution.platform_families import matches_service_module_source
from ..resolution.platform_families import terraform_platform_evidence_kind

__all__ = [
    "TerraformRuntimeFamily",
    "format_platform_kind_label",
    "infer_infrastructure_runtime_family_kind",
    "infer_runtime_family_kind_from_identifiers",
    "infer_terraform_runtime_family_kind",
    "iter_runtime_families",
    "lookup_runtime_family",
    "matches_service_module_source",
    "terraform_platform_evidence_kind",
]

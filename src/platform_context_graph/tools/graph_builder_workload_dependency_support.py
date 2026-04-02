"""Compatibility facade for workload dependency helpers."""

from ..resolution.workloads.dependency_support import (
    _load_runtime_dependency_targets,
)
from ..resolution.workloads.dependency_support import materialize_runtime_dependencies

__all__ = ["_load_runtime_dependency_targets", "materialize_runtime_dependencies"]

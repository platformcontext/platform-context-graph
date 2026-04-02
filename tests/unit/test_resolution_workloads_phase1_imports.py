"""Phase 1 import checks for canonical workload resolution helpers."""

from __future__ import annotations

from platform_context_graph.resolution.workloads.dependency_support import (
    _load_runtime_dependency_targets as canonical_load_targets,
)
from platform_context_graph.resolution.workloads.materialization import (
    materialize_workloads as canonical_materialize_workloads,
)
from platform_context_graph.tools.graph_builder_workload_dependency_support import (
    _load_runtime_dependency_targets as legacy_load_targets,
)
from platform_context_graph.tools.graph_builder_workloads import (
    materialize_workloads as legacy_materialize_workloads,
)


def test_legacy_workload_helpers_point_at_resolution_modules() -> None:
    """Legacy workload modules should re-export canonical resolution helpers."""

    assert legacy_materialize_workloads is canonical_materialize_workloads
    assert legacy_load_targets is canonical_load_targets

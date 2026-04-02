"""Phase 1 import checks for canonical resolution platform helpers."""

from __future__ import annotations

from platform_context_graph.resolution.platforms import (
    infer_gitops_platform_id as canonical_infer_gitops_platform_id,
)
from platform_context_graph.resolution.platforms import (
    infer_gitops_platform_kind as canonical_infer_gitops_platform_kind,
)
from platform_context_graph.resolution.platforms import (
    infer_infrastructure_platform_descriptor as canonical_infer_descriptor,
)
from platform_context_graph.tools.graph_builder_platforms import (
    infer_gitops_platform_id as legacy_infer_gitops_platform_id,
)
from platform_context_graph.tools.graph_builder_platforms import (
    infer_gitops_platform_kind as legacy_infer_gitops_platform_kind,
)
from platform_context_graph.tools.graph_builder_platforms import (
    infer_infrastructure_platform_descriptor as legacy_infer_descriptor,
)


def test_legacy_platform_helpers_point_at_resolution_module() -> None:
    """Legacy platform helpers should re-export canonical resolution helpers."""

    assert legacy_infer_gitops_platform_id is canonical_infer_gitops_platform_id
    assert legacy_infer_gitops_platform_kind is canonical_infer_gitops_platform_kind
    assert legacy_infer_descriptor is canonical_infer_descriptor

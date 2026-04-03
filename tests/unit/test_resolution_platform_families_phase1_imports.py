"""Phase 1 import checks for canonical runtime platform family helpers."""

from __future__ import annotations

from platform_context_graph.resolution.platform_families import (
    format_platform_kind_label as canonical_format_platform_kind_label,
)
from platform_context_graph.resolution.platform_families import (
    lookup_runtime_family as canonical_lookup_runtime_family,
)
from platform_context_graph.tools.runtime_platform_families import (
    format_platform_kind_label as legacy_format_platform_kind_label,
)
from platform_context_graph.tools.runtime_platform_families import (
    lookup_runtime_family as legacy_lookup_runtime_family,
)


def test_legacy_runtime_platform_family_helpers_reexport_resolution_module() -> None:
    """Legacy runtime family helpers should re-export canonical resolution ones."""

    assert legacy_format_platform_kind_label is canonical_format_platform_kind_label
    assert legacy_lookup_runtime_family is canonical_lookup_runtime_family

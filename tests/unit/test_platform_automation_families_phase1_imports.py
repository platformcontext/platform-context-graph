"""Phase 1 import compatibility tests for automation runtime families."""

from platform_context_graph.platform.automation_families import (
    infer_automation_runtime_families as new_infer_automation_runtime_families,
)
from platform_context_graph.tools.runtime_automation_families import (
    infer_automation_runtime_families as legacy_infer_automation_runtime_families,
)


def test_automation_runtime_families_move_to_platform_package() -> None:
    """Expose automation family helpers from the canonical platform package."""
    assert new_infer_automation_runtime_families.__module__ == (
        "platform_context_graph.platform.automation_families"
    )


def test_legacy_automation_family_import_reexports_canonical_api() -> None:
    """Keep legacy automation family imports working during Phase 1."""
    assert (
        legacy_infer_automation_runtime_families
        is new_infer_automation_runtime_families
    )

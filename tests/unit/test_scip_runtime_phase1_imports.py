"""Phase 1 import compatibility tests for canonical SCIP runtime modules."""

from platform_context_graph.parsers.scip.indexer import (
    EXTENSION_TO_SCIP as new_extension_to_scip,
)
from platform_context_graph.parsers.scip.indexer import (
    ScipIndexer as NewScipIndexer,
)
from platform_context_graph.parsers.scip.indexer import (
    detect_project_lang as new_detect_project_lang,
)
from platform_context_graph.parsers.scip.indexer import (
    is_scip_available as new_is_scip_available,
)
from platform_context_graph.parsers.scip.parser import ScipIndexParser as NewParser
from platform_context_graph.tools.scip_indexer import (
    EXTENSION_TO_SCIP as legacy_extension_to_scip,
)
from platform_context_graph.tools.scip_indexer import (
    ScipIndexer as LegacyScipIndexer,
)
from platform_context_graph.tools.scip_indexer import (
    detect_project_lang as legacy_detect_project_lang,
)
from platform_context_graph.tools.scip_indexer import (
    is_scip_available as legacy_is_scip_available,
)
from platform_context_graph.tools.scip_parser import ScipIndexParser as LegacyParser


def test_scip_runtime_modules_move_to_parsers_package() -> None:
    """Expose SCIP parser and runtime helpers from canonical parser packages."""
    assert NewParser.__module__ == "platform_context_graph.parsers.scip.parser"
    assert NewScipIndexer.__module__ == "platform_context_graph.parsers.scip.support"
    assert new_detect_project_lang.__module__ == (
        "platform_context_graph.parsers.scip.support"
    )
    assert new_is_scip_available.__module__ == (
        "platform_context_graph.parsers.scip.support"
    )
    assert new_extension_to_scip is not None


def test_legacy_scip_runtime_imports_reexport_canonical_modules() -> None:
    """Keep legacy SCIP imports working during the Phase 1 transition."""
    assert LegacyParser is NewParser
    assert LegacyScipIndexer is NewScipIndexer
    assert legacy_detect_project_lang is new_detect_project_lang
    assert legacy_is_scip_available is new_is_scip_available
    assert legacy_extension_to_scip is new_extension_to_scip

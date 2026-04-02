"""Phase 1 import compatibility tests for the parser registry move."""

from platform_context_graph.parsers.registry import (
    TreeSitterParser as NewTreeSitterParser,
)
from platform_context_graph.parsers.registry import (
    build_parser_registry as new_build_parser_registry,
)
from platform_context_graph.parsers.registry import parse_file as new_parse_file
from platform_context_graph.parsers.registry import (
    parse_file_for_indexing_worker as new_parse_file_for_indexing_worker,
)
from platform_context_graph.parsers.registry import (
    pre_scan_for_imports as new_pre_scan_for_imports,
)
from platform_context_graph.tools.graph_builder_parsers import (
    TreeSitterParser as LegacyTreeSitterParser,
)
from platform_context_graph.tools.graph_builder_parsers import (
    build_parser_registry as legacy_build_parser_registry,
)
from platform_context_graph.tools.graph_builder_parsers import (
    parse_file as legacy_parse_file,
)
from platform_context_graph.tools.graph_builder_parsers import (
    parse_file_for_indexing_worker as legacy_parse_file_for_indexing_worker,
)
from platform_context_graph.tools.graph_builder_parsers import (
    pre_scan_for_imports as legacy_pre_scan_for_imports,
)


def test_parser_registry_moves_to_parsers_package() -> None:
    """Expose parser registry helpers from the canonical parsers package."""
    assert NewTreeSitterParser.__module__ == "platform_context_graph.parsers.registry"
    assert new_build_parser_registry.__module__ == (
        "platform_context_graph.parsers.registry"
    )
    assert new_parse_file.__module__ == "platform_context_graph.parsers.registry"
    assert new_parse_file_for_indexing_worker.__module__ == (
        "platform_context_graph.parsers.registry"
    )
    assert new_pre_scan_for_imports.__module__ == (
        "platform_context_graph.parsers.registry"
    )


def test_legacy_parser_registry_imports_reexport_new_api() -> None:
    """Keep legacy parser registry imports working during Phase 1."""
    assert issubclass(LegacyTreeSitterParser, NewTreeSitterParser)
    assert legacy_build_parser_registry is not None
    assert legacy_parse_file is not None
    assert legacy_parse_file_for_indexing_worker is not None
    assert legacy_pre_scan_for_imports is not None

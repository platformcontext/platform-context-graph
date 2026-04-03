"""Phase 1 import compatibility tests for raw-text parser helpers."""

from platform_context_graph.parsers.raw_text import (
    DOCKERFILE_PARSER_KEY as new_dockerfile_parser_key,
)
from platform_context_graph.parsers.raw_text import (
    RawTextParser as NewRawTextParser,
)
from platform_context_graph.parsers.raw_text import (
    parser_key_for_path as new_parser_key_for_path,
)
from platform_context_graph.parsers.raw_text import (
    register_raw_text_parsers as new_register_raw_text_parsers,
)
from platform_context_graph.tools.graph_builder_raw_text import (
    DOCKERFILE_PARSER_KEY as legacy_dockerfile_parser_key,
)
from platform_context_graph.tools.graph_builder_raw_text import (
    RawTextParser as LegacyRawTextParser,
)
from platform_context_graph.tools.graph_builder_raw_text import (
    parser_key_for_path as legacy_parser_key_for_path,
)
from platform_context_graph.tools.graph_builder_raw_text import (
    register_raw_text_parsers as legacy_register_raw_text_parsers,
)


def test_raw_text_helpers_move_to_parsers_package() -> None:
    """Expose raw-text parser helpers from the canonical parsers package."""
    assert NewRawTextParser.__module__ == "platform_context_graph.parsers.raw_text"
    assert new_parser_key_for_path.__module__ == (
        "platform_context_graph.parsers.raw_text"
    )
    assert new_register_raw_text_parsers.__module__ == (
        "platform_context_graph.parsers.raw_text"
    )
    assert new_dockerfile_parser_key == "__dockerfile__"


def test_legacy_raw_text_imports_reexport_new_api() -> None:
    """Keep legacy raw-text parser imports working during Phase 1."""
    assert LegacyRawTextParser is NewRawTextParser
    assert legacy_parser_key_for_path is new_parser_key_for_path
    assert legacy_register_raw_text_parsers is new_register_raw_text_parsers
    assert legacy_dockerfile_parser_key == new_dockerfile_parser_key

"""Compatibility exports for the parser capabilities package move."""

from platform_context_graph.parsers.capabilities import (
    expected_generated_language_docs,
    load_language_capability_specs,
    render_feature_matrix,
    render_language_doc,
    validate_language_capability_specs,
    write_generated_language_docs,
)

__all__ = (
    "expected_generated_language_docs",
    "load_language_capability_specs",
    "render_feature_matrix",
    "render_language_doc",
    "validate_language_capability_specs",
    "write_generated_language_docs",
)

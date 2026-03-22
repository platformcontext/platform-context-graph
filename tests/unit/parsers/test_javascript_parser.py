"""Tests for the handwritten JavaScript parser facade and support module."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.javascript import (
    JavascriptTreeSitterParser,
)
from platform_context_graph.tools.languages.javascript_support import (
    pre_scan_javascript,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def javascript_parser() -> JavascriptTreeSitterParser:
    """Build a JavaScript parser when the grammar is available."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("javascript"):
        pytest.skip(
            "JavaScript tree-sitter grammar is not available in this environment"
        )

    wrapper = MagicMock()
    wrapper.language_name = "javascript"
    wrapper.language = manager.get_language_safe("javascript")
    wrapper.parser = manager.create_parser("javascript")
    return JavascriptTreeSitterParser(wrapper)


def test_parse_javascript_simple_declarations(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Parse a small JavaScript file and verify key declarations are captured."""
    source = """
import fs from "node:fs";

class Greeter {
  greet(name) {
    return name;
  }
}

const hello = function helloWorld(value) {
  return value;
};
"""
    source_file = temp_test_dir / "sample.js"
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    assert any(item["name"] == "Greeter" for item in result["classes"])
    assert any(item["name"] == "hello" for item in result["functions"])
    assert any(item["name"] == "node:fs" for item in result["imports"])


def test_pre_scan_javascript_keeps_public_import_surface(temp_test_dir) -> None:
    """Return a name-to-file map through the JavaScript support module."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("javascript"):
        pytest.skip(
            "JavaScript tree-sitter grammar is not available in this environment"
        )

    wrapper = MagicMock()
    wrapper.language_name = "javascript"
    wrapper.language = manager.get_language_safe("javascript")
    wrapper.parser = manager.create_parser("javascript")

    source_file = temp_test_dir / "prescan_sample.js"
    source_file.write_text(
        "class Greeter {}\nfunction hello() {}\nconst world = () => world;\n",
        encoding="utf-8",
    )

    imports_map = pre_scan_javascript([source_file], wrapper)

    assert imports_map["Greeter"] == [str(source_file.resolve())]
    assert imports_map["hello"] == [str(source_file.resolve())]

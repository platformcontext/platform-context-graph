"""Tests for the handwritten Swift parser facade."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.swift import (
    SwiftTreeSitterParser,
    pre_scan_swift,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def swift_parser():
    """Build a Swift parser when the grammar is available."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("swift"):
        pytest.skip("Swift tree-sitter grammar is not available in this environment")

    wrapper = MagicMock()
    wrapper.language_name = "swift"
    wrapper.language = manager.get_language_safe("swift")
    wrapper.parser = manager.create_parser("swift")
    return SwiftTreeSitterParser(wrapper)


def test_parse_swift_declarations_with_current_grammar(swift_parser, temp_test_dir):
    """Parse common Swift declarations with the current grammar."""
    code = """
import Foundation

struct MetricTracker {
    let sampleCount: Int
    func record(value: Int) {
        print(value)
    }
}

enum ProcessingState {
    case idle
    case running
}

actor TaskWorker {
    func compute() {}
}

class GenericController {
    let name: String

    init(name: String) {
        self.name = name
    }

    func track() {
        print(name)
    }
}
"""
    f = temp_test_dir / "sample.swift"
    f.write_text(code)

    result = swift_parser.parse(f)

    assert len(result["functions"]) >= 4
    assert any(item["name"] == "MetricTracker" for item in result["structs"])
    assert any(item["name"] == "ProcessingState" for item in result["enums"])
    assert any(item["name"] == "TaskWorker" for item in result["classes"])
    assert any(item["name"] == "GenericController" for item in result["classes"])
    assert len(result["imports"]) == 1
    assert any(item["name"] == "sampleCount" for item in result["variables"])


def test_pre_scan_swift_keeps_public_import_surface(temp_test_dir) -> None:
    """Return a type-to-file map through the legacy module import path."""
    source_file = temp_test_dir / "prescan_sample.swift"
    source_file.write_text(
        "struct MetricTracker {}\nclass GenericController {}\n",
        encoding="utf-8",
    )

    imports_map = pre_scan_swift([source_file], MagicMock())

    assert imports_map["MetricTracker"] == [str(source_file)]
    assert imports_map["GenericController"] == [str(source_file)]

"""Tests for the handwritten Ruby parser facade."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.ruby import (
    RubyTreeSitterParser,
    pre_scan_ruby,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def ruby_parser() -> RubyTreeSitterParser:
    """Build a Ruby parser when the grammar is available."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("ruby"):
        pytest.skip("Ruby tree-sitter grammar is not available in this environment")

    wrapper = MagicMock()
    wrapper.language_name = "ruby"
    wrapper.language = manager.get_language_safe("ruby")
    wrapper.parser = manager.create_parser("ruby")
    return RubyTreeSitterParser(wrapper)


def test_parse_ruby_definitions(
    ruby_parser: RubyTreeSitterParser, temp_test_dir
) -> None:
    """Parse a small Ruby file and preserve the public parse surface."""
    source_file = temp_test_dir / "sample.rb"
    source_file.write_text(
        """module MyApp
  class Worker
    def perform(task)
      task.call
    end
  end
end
""",
        encoding="utf-8",
    )

    result = ruby_parser.parse(source_file)

    assert result["lang"] == "ruby"
    assert any(item["name"] == "MyApp" for item in result["modules"])
    assert any(item["name"] == "Worker" for item in result["classes"])
    assert any(item["name"] == "perform" for item in result["functions"])


def test_pre_scan_ruby_keeps_public_import_surface(temp_test_dir) -> None:
    """Return a name-to-file map through the legacy module import path."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("ruby"):
        pytest.skip("Ruby tree-sitter grammar is not available in this environment")

    wrapper = MagicMock()
    wrapper.language_name = "ruby"
    wrapper.language = manager.get_language_safe("ruby")
    wrapper.parser = manager.create_parser("ruby")

    source_file = temp_test_dir / "prescan_sample.rb"
    source_file.write_text(
        """module MyApp
  class Worker
    def perform
    end
  end
end
""",
        encoding="utf-8",
    )

    imports_map = pre_scan_ruby([source_file], wrapper)

    assert imports_map["MyApp"] == [str(source_file.resolve())]
    assert imports_map["Worker"] == [str(source_file.resolve())]
    assert imports_map["perform"] == [str(source_file.resolve())]

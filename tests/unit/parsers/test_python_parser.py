"""Tests for the handwritten Python parser facade."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.python import (
    PythonTreeSitterParser,
    pre_scan_python,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


class TestPythonParser:
    """Test the Python parser logic."""

    @pytest.fixture(scope="class")
    def parser(self):
        """Build a parser instance backed by the real tree-sitter grammar."""
        # We need to construct a PythonTreeSitterParser
        # It takes a wrapper. Let's mock the wrapper or create a real one.
        # Real one:
        manager = get_tree_sitter_manager()

        # Create a mock wrapper that behaves like the one expected by PythonTreeSitterParser
        wrapper = MagicMock()
        wrapper.language_name = "python"
        wrapper.language = manager.get_language_safe("python")
        wrapper.parser = manager.create_parser("python")

        return PythonTreeSitterParser(wrapper)

    def test_parse_simple_function(self, parser, temp_test_dir):
        """Parse a simple python file and verify output."""
        code = "def hello():\n    print('world')"
        f = temp_test_dir / "test.py"
        f.write_text(code)

        # Act
        result = parser.parse(str(f))

        # Assert
        # We expect a list of nodes/edges or a structure containing them
        # This structure depends on the actual return type of .parse()
        # For now, I will assert keys exist.

        print(f"DEBUG: Parser result keys: {result.keys()}")

        assert "functions" in result
        funcs = result["functions"]
        assert len(funcs) == 1
        assert funcs[0]["name"] == "hello"

    def test_parse_class_with_method(self, parser, temp_test_dir):
        """Parse a class with a method."""
        code = """
class Greeter:
    def greet(self, name):
        return f"Hello {name}"
"""
        f = temp_test_dir / "classes.py"
        f.write_text(code)

        result = parser.parse(str(f))

        assert "classes" in result
        classes = result["classes"]
        assert len(classes) == 1
        assert classes[0]["name"] == "Greeter"

        # Check methods if they are nested or separate
        # Depending on implementation, methods might be in 'functions' with parent info
        # or inside 'classes'.
        # Let's assume they are captured.

    def test_pre_scan_python_keeps_public_import_surface(self, temp_test_dir) -> None:
        """Return a name-to-file map through the legacy module import path."""
        manager = get_tree_sitter_manager()
        wrapper = MagicMock()
        wrapper.language_name = "python"
        wrapper.language = manager.get_language_safe("python")
        wrapper.parser = manager.create_parser("python")

        source_file = temp_test_dir / "prescan_sample.py"
        source_file.write_text(
            "class Greeter:\n    pass\n\n\ndef greet(name):\n    return name\n",
            encoding="utf-8",
        )

        imports_map = pre_scan_python([source_file], wrapper)

        assert imports_map["Greeter"] == [str(source_file.resolve())]
        assert imports_map["greet"] == [str(source_file.resolve())]

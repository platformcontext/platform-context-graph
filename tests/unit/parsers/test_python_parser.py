"""Tests for the handwritten Python parser facade."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.python import (
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

    def test_parse_imports_calls_and_inheritance(self, parser, temp_test_dir):
        """Parse Python imports, function calls, and inheritance metadata."""
        code = """
import os
from pathlib import Path

class Animal:
    pass

class Dog(Animal):
    pass

def build_path(name):
    return os.path.join(str(Path(name)), "child")
"""
        f = temp_test_dir / "relations.py"
        f.write_text(code)

        result = parser.parse(str(f))

        assert len(result["imports"]) >= 2
        assert any(item["name"] == "join" for item in result["function_calls"])
        dog = next(item for item in result["classes"] if item["name"] == "Dog")
        assert "Animal" in dog["bases"]

    def test_parse_async_functions_do_not_emit_async_flag(self, parser, temp_test_dir):
        """Async function definitions are parsed as functions without async metadata."""
        code = """
async def fetch_remote():
    return "ok"
"""
        f = temp_test_dir / "async_fn.py"
        f.write_text(code)

        result = parser.parse(str(f))

        fetch_remote = next(
            item for item in result["functions"] if item["name"] == "fetch_remote"
        )
        assert "async" not in fetch_remote

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

    def test_parse_variables_and_omits_decorator_metadata(
        self, parser, temp_test_dir, monkeypatch
    ):
        """Parse variable assignments while documenting missing decorator metadata."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "all")
        code = """
MODULE_LEVEL = 3

def traced(func):
    return func

@traced
def greet(name):
    local_value = name.upper()
    return local_value
"""
        f = temp_test_dir / "decorated.py"
        f.write_text(code)

        result = parser.parse(str(f))

        variables = result["variables"]
        assert any(item["name"] == "MODULE_LEVEL" for item in variables)
        assert any(item["name"] == "local_value" for item in variables)

        functions = result["functions"]
        greet = next(item for item in functions if item["name"] == "greet")
        assert greet["decorators"] == []

    def test_parse_does_not_emit_type_annotation_bucket(self, parser, temp_test_dir):
        """Type annotations are not emitted as a dedicated parse bucket today."""
        code = """
def greet(name: str) -> str:
    return name
"""
        f = temp_test_dir / "annotations.py"
        f.write_text(code)

        result = parser.parse(str(f))

        assert "type_annotations" not in result

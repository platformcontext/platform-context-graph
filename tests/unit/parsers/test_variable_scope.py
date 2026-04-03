"""Tests for PCG_VARIABLE_SCOPE scope-filtering of variable extraction."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


class TestPythonVariableScope:
    """Verify module-scope filtering for Python variable extraction."""

    @pytest.fixture(scope="class")
    def parser(self):
        """Build a Python parser backed by the real tree-sitter grammar."""
        from platform_context_graph.parsers.languages.python import (
            PythonTreeSitterParser,
        )

        manager = get_tree_sitter_manager()
        wrapper = MagicMock()
        wrapper.language_name = "python"
        wrapper.language = manager.get_language_safe("python")
        wrapper.parser = manager.create_parser("python")
        return PythonTreeSitterParser(wrapper)

    @pytest.fixture()
    def source_file(self, temp_test_dir):
        """Write a Python file with module, class, and function-local vars."""
        code = """\
MODULE_VAR = "hello"
ANOTHER_MODULE = 42

class Config:
    CLASS_VAR = True
    OTHER_CLASS = "yes"

    def method(self):
        method_local = 1
        return method_local

def helper():
    func_local = "temp"
    loop_counter = 0
    for loop_counter in range(10):
        pass
    return func_local
"""
        path = temp_test_dir / "scope_test.py"
        path.write_text(code)
        return path

    def test_module_scope_extracts_only_module_and_class_vars(
        self, parser, source_file, monkeypatch
    ):
        """With scope=module, only module-level and class-level vars appear."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "module")
        result = parser.parse(str(source_file))

        var_names = {v["name"] for v in result["variables"]}
        assert "MODULE_VAR" in var_names
        assert "ANOTHER_MODULE" in var_names
        assert "CLASS_VAR" in var_names
        assert "OTHER_CLASS" in var_names
        assert "method_local" not in var_names
        assert "func_local" not in var_names
        assert "loop_counter" not in var_names

    def test_all_scope_extracts_every_assignment(
        self, parser, source_file, monkeypatch
    ):
        """With scope=all, every assignment including function-local ones appear."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "all")
        result = parser.parse(str(source_file))

        var_names = {v["name"] for v in result["variables"]}
        assert "MODULE_VAR" in var_names
        assert "CLASS_VAR" in var_names
        assert "method_local" in var_names
        assert "func_local" in var_names

    def test_default_scope_is_module(self, parser, source_file, monkeypatch):
        """When PCG_VARIABLE_SCOPE is unset, the default is module scope."""
        monkeypatch.delenv("PCG_VARIABLE_SCOPE", raising=False)
        result = parser.parse(str(source_file))

        var_names = {v["name"] for v in result["variables"]}
        assert "MODULE_VAR" in var_names
        assert "CLASS_VAR" in var_names
        assert "func_local" not in var_names


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


class TestGoVariableScope:
    """Verify module-scope filtering for Go variable extraction."""

    @pytest.fixture(scope="class")
    def parser(self):
        """Build a Go parser backed by the real tree-sitter grammar."""
        from platform_context_graph.parsers.languages.go import GoTreeSitterParser

        manager = get_tree_sitter_manager()
        if not manager.is_language_available("go"):
            pytest.skip("Go tree-sitter grammar not available")
        wrapper = MagicMock()
        wrapper.language_name = "go"
        wrapper.language = manager.get_language_safe("go")
        wrapper.parser = manager.create_parser("go")
        return GoTreeSitterParser(wrapper)

    @pytest.fixture()
    def source_file(self, temp_test_dir):
        """Write a Go file with package-level and function-local vars."""
        code = """\
package main

var Version = "1.0.0"
var BuildDate string

const MaxRetries = 3

func helper() {
    localVar := "temp"
    var innerVar = 10
    _ = localVar
    _ = innerVar
}
"""
        path = temp_test_dir / "scope_test.go"
        path.write_text(code)
        return path

    def test_module_scope_extracts_only_toplevel_vars(
        self, parser, source_file, monkeypatch
    ):
        """With scope=module, only package-level var/const are extracted."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "module")
        result = parser.parse(source_file)

        var_names = {v["name"] for v in result["variables"]}
        assert "Version" in var_names
        assert "BuildDate" in var_names
        assert "MaxRetries" in var_names
        assert "localVar" not in var_names
        assert "innerVar" not in var_names

    def test_all_scope_extracts_every_declaration(
        self, parser, source_file, monkeypatch
    ):
        """With scope=all, every var/const/:= including function-local ones appear."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "all")
        result = parser.parse(source_file)

        var_names = {v["name"] for v in result["variables"]}
        assert "Version" in var_names
        assert "MaxRetries" in var_names
        assert "localVar" in var_names
        assert "innerVar" in var_names

    def test_default_scope_is_module(self, parser, source_file, monkeypatch):
        """When PCG_VARIABLE_SCOPE is unset, the default is module scope."""
        monkeypatch.delenv("PCG_VARIABLE_SCOPE", raising=False)
        result = parser.parse(source_file)

        var_names = {v["name"] for v in result["variables"]}
        assert "Version" in var_names
        assert "MaxRetries" in var_names
        assert "localVar" not in var_names


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------


class TestTypeScriptVariableScope:
    """Verify module-scope filtering for TypeScript variable extraction."""

    @pytest.fixture(scope="class")
    def parser(self):
        """Build a TypeScript parser backed by the real tree-sitter grammar."""
        from platform_context_graph.parsers.languages.typescript import (
            TypescriptTreeSitterParser,
        )

        manager = get_tree_sitter_manager()
        if not manager.is_language_available("typescript"):
            pytest.skip("TypeScript tree-sitter grammar not available")
        wrapper = MagicMock()
        wrapper.language_name = "typescript"
        wrapper.language = manager.get_language_safe("typescript")
        wrapper.parser = manager.create_parser("typescript")
        return TypescriptTreeSitterParser(wrapper)

    @pytest.fixture()
    def source_file(self, temp_test_dir):
        """Write a TS file with module-level, exported, and function-local vars."""
        code = """\
const VERSION = "1.0.0";
let counter = 0;
export const API_KEY = "abc123";

function helper() {
    const localVar = "temp";
    let loopIdx = 0;
    for (loopIdx = 0; loopIdx < 10; loopIdx++) {}
    return localVar;
}

class Service {
    start() {
        const innerVar = true;
    }
}
"""
        path = temp_test_dir / "scope_test.ts"
        path.write_text(code)
        return path

    def test_module_scope_extracts_only_toplevel_vars(
        self, parser, source_file, monkeypatch
    ):
        """With scope=module, only program-level and exported vars appear."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "module")
        result = parser.parse(source_file)

        var_names = {v["name"] for v in result["variables"]}
        assert "VERSION" in var_names
        assert "counter" in var_names
        assert "API_KEY" in var_names
        assert "localVar" not in var_names
        assert "loopIdx" not in var_names
        assert "innerVar" not in var_names

    def test_all_scope_extracts_every_declaration(
        self, parser, source_file, monkeypatch
    ):
        """With scope=all, every declaration including function-local ones appear."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "all")
        result = parser.parse(source_file)

        var_names = {v["name"] for v in result["variables"]}
        assert "VERSION" in var_names
        assert "API_KEY" in var_names
        assert "localVar" in var_names
        assert "innerVar" in var_names

    def test_default_scope_is_module(self, parser, source_file, monkeypatch):
        """When PCG_VARIABLE_SCOPE is unset, the default is module scope."""
        monkeypatch.delenv("PCG_VARIABLE_SCOPE", raising=False)
        result = parser.parse(source_file)

        var_names = {v["name"] for v in result["variables"]}
        assert "VERSION" in var_names
        assert "counter" in var_names
        assert "API_KEY" in var_names
        assert "localVar" not in var_names

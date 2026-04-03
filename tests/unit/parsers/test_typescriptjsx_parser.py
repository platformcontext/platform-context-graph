"""Tests for the TypeScript JSX parser."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.typescriptjsx import (
    TypescriptJSXTreeSitterParser,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def tsx_parser() -> TypescriptJSXTreeSitterParser:
    """Build a TSX parser backed by the TypeScript grammar."""

    manager = get_tree_sitter_manager()
    if not manager.is_language_available("typescript"):
        pytest.skip("TypeScript tree-sitter grammar not available")

    wrapper = MagicMock()
    wrapper.language_name = "typescript"
    wrapper.language = manager.get_language_safe("typescript")
    wrapper.parser = manager.create_parser("typescript")
    return TypescriptJSXTreeSitterParser(wrapper)


def test_parse_tsx_components_and_interfaces(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir
) -> None:
    """Parse TSX files with React components, interfaces, and calls."""

    source = """\
import React from 'react';

interface ButtonProps {
  label: string;
}

export function Button({ label }: ButtonProps) {
  return <button>{label}</button>;
}
"""
    path = temp_test_dir / "Button.tsx"
    path.write_text(source, encoding="utf-8")

    result = tsx_parser.parse(path)

    assert result["lang"] == "typescript"
    assert any(item["name"] == "Button" for item in result["functions"])
    assert any(item["name"] == "ButtonProps" for item in result["interfaces"])
    assert any(item["name"] == "Button" for item in result["components"])
    assert len(result["imports"]) >= 1


def test_parse_tsx_result_structure(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir
) -> None:
    """Expose the canonical TSX parser buckets expected by docs/specs."""

    path = temp_test_dir / "App.tsx"
    path.write_text("export const App = () => <div>Hello</div>;\n", encoding="utf-8")

    result = tsx_parser.parse(path)

    assert result["path"] == str(path)
    assert result["lang"] == "typescript"
    assert "functions" in result
    assert "classes" in result
    assert "interfaces" in result
    assert "type_aliases" in result
    assert "components" in result


def test_parse_tsx_class_components(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir
) -> None:
    """Parse class-based TSX components into class and function entities."""

    source = """\
import React from 'react';

export class LegacyWidget extends React.Component {
  render() {
    return <div>Hello</div>;
  }
}
"""
    path = temp_test_dir / "LegacyWidget.tsx"
    path.write_text(source, encoding="utf-8")

    result = tsx_parser.parse(path)

    assert any(item["name"] == "LegacyWidget" for item in result["classes"])
    assert any(item["name"] == "render" for item in result["functions"])


def test_parse_tsx_imports_calls_variables_and_type_aliases(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir, monkeypatch
) -> None:
    """Parse TSX constructs that feed the capability checklist."""
    monkeypatch.setenv("PCG_VARIABLE_SCOPE", "all")

    source = """\
import { useMemo } from 'react';

type User = {
  id: string;
};

export function Example() {
  const total = useMemo(() => 1 + 1, []);
  return <div>{total}</div>;
}
"""
    path = temp_test_dir / "Example.tsx"
    path.write_text(source, encoding="utf-8")

    result = tsx_parser.parse(path)

    assert any(item["source"] == "react" for item in result["imports"])
    assert any(item["name"] == "useMemo" for item in result["function_calls"])
    assert any(item["name"] == "total" for item in result["variables"])
    assert any(item["name"] == "User" for item in result["type_aliases"])

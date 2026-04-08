"""Tests for the TypeScript JSX parser."""

from __future__ import annotations

import base64
import gzip
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.typescriptjsx import (
    TypescriptJSXTreeSitterParser,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def tsx_parser() -> TypescriptJSXTreeSitterParser:
    """Build a TSX parser backed by the TSX grammar."""

    manager = get_tree_sitter_manager()
    if not manager.is_language_available("tsx"):
        pytest.skip("TSX tree-sitter grammar not available")

    wrapper = MagicMock()
    wrapper.language_name = "tsx"
    wrapper.language = manager.get_language_safe("tsx")
    wrapper.parser = manager.create_parser("tsx")
    return TypescriptJSXTreeSitterParser(wrapper)


def _load_fixture_text(fixture_name: str) -> str:
    """Decode a compressed TSX fixture into UTF-8 source text."""

    fixture_path = (
        Path(__file__).resolve().parents[2] / "fixtures" / "parsers" / fixture_name
    )
    encoded_fixture = fixture_path.read_text(encoding="utf-8")
    return gzip.decompress(base64.b64decode(encoded_fixture)).decode("utf-8")


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


def test_parse_tsx_ignores_error_recovery_method_captures(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir
) -> None:
    """Ignore bogus method captures recovered from invalid TSX parser states."""

    path = temp_test_dir / "search-boats-regression.tsx"
    path.write_text(
        _load_fixture_text("typescriptjsx_search_boats_regression.tsx.gz.b64"),
        encoding="utf-8",
    )

    result = tsx_parser.parse(path)

    function_names = {item["name"] for item in result["functions"]}
    max_arg_length = max(
        (len(arg) for item in result["functions"] for arg in item.get("args", [])),
        default=0,
    )

    assert "if" not in function_names
    assert max_arg_length < 200


def test_parse_tsx_destructured_typed_props_as_bound_names(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir
) -> None:
    """Normalize destructured typed props into stable bound parameter names."""

    source = """\
type GridProps<T> = {
  data: T[];
  loading?: boolean;
  sorting?: string[];
  selectedRows?: Set<string>;
  onSortingChange?: (sorting: string[]) => void;
};

const DataGrid = <T extends Record<string, unknown>>({
  data,
  loading = false,
  sorting: controlledSorting,
  selectedRows = new Set(),
  onSortingChange,
}: GridProps<T>) => {
  return <div>{data.length}{String(loading)}{String(controlledSorting)}{selectedRows.size}{String(onSortingChange)}</div>;
};
"""
    path = temp_test_dir / "DataGridProps.tsx"
    path.write_text(source, encoding="utf-8")

    result = tsx_parser.parse(path)

    data_grid = next(item for item in result["functions"] if item["name"] == "DataGrid")
    assert data_grid["args"] == [
        "data",
        "loading",
        "controlledSorting",
        "selectedRows",
        "onSortingChange",
    ]


def test_parse_tsx_next_page_semantics(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir
) -> None:
    """Expose Next.js page semantics and metadata exports for app-router pages."""

    page_dir = temp_test_dir / "src" / "app" / "[locale]" / "boats"
    page_dir.mkdir(parents=True)
    page_file = page_dir / "page.tsx"
    page_file.write_text(
        """\
import type { Metadata } from 'next';

export async function generateMetadata(): Promise<Metadata> {
  return { title: 'Boats' };
}

export default async function BoatsPage() {
  return <div>Boats</div>;
}
""",
        encoding="utf-8",
    )

    result = tsx_parser.parse(page_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["nextjs", "react"]
    assert semantics["react"]["boundary"] == "shared"
    assert semantics["react"]["component_exports"] == ["BoatsPage"]
    assert semantics["react"]["hooks_used"] == []
    assert semantics["nextjs"]["module_kind"] == "page"
    assert semantics["nextjs"]["metadata_exports"] == "dynamic"
    assert semantics["nextjs"]["route_segments"] == ["[locale]", "boats"]
    assert semantics["nextjs"]["runtime_boundary"] == "server"


def test_parse_tsx_next_layout_semantics(
    tsx_parser: TypescriptJSXTreeSitterParser, temp_test_dir
) -> None:
    """Expose Next.js layout semantics for app-router layout modules."""

    layout_dir = temp_test_dir / "src" / "app" / "dashboard"
    layout_dir.mkdir(parents=True)
    layout_file = layout_dir / "layout.tsx"
    layout_file.write_text(
        """\
import type { ReactNode } from 'react';

export default function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  return <section>{children}</section>;
}
""",
        encoding="utf-8",
    )

    result = tsx_parser.parse(layout_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["nextjs", "react"]
    assert semantics["react"]["boundary"] == "shared"
    assert semantics["react"]["component_exports"] == ["DashboardLayout"]
    assert semantics["nextjs"]["module_kind"] == "layout"
    assert semantics["nextjs"]["metadata_exports"] == "none"
    assert semantics["nextjs"]["route_segments"] == ["dashboard"]

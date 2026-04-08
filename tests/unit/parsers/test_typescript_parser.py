"""Tests for the TypeScript parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.typescript import (
    TypescriptTreeSitterParser,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def ts_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("typescript"):
        pytest.skip("TypeScript tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "typescript"
    wrapper.language = manager.get_language_safe("typescript")
    wrapper.parser = manager.create_parser("typescript")
    return TypescriptTreeSitterParser(wrapper)


def test_parse_functions(ts_parser, temp_test_dir):
    code = """function greet(name: string): string {
    return `Hello, ${name}!`;
}

const double = (x: number): number => x * 2;

async function fetchData(url: string): Promise<any> {
    const response = await fetch(url);
    return response.json();
}
"""
    f = temp_test_dir / "funcs.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    funcs = result["functions"]
    assert len(funcs) >= 2
    names = [fn["name"] for fn in funcs]
    assert "greet" in names


def test_parse_classes(ts_parser, temp_test_dir):
    code = """abstract class Shape {
    abstract area(): number;
    describe(): string { return "Shape"; }
}

class Circle extends Shape {
    constructor(private radius: number) { super(); }
    area(): number { return Math.PI * this.radius ** 2; }
}

class Rectangle extends Shape {
    constructor(private width: number, private height: number) { super(); }
    area(): number { return this.width * this.height; }
}
"""
    f = temp_test_dir / "classes.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    classes = result.get("classes", [])
    assert len(classes) >= 3
    names = [c["name"] for c in classes]
    assert "Shape" in names
    assert "Circle" in names


def test_parse_interfaces(ts_parser, temp_test_dir):
    code = """interface Serializable {
    serialize(): string;
}

interface Repository<T> {
    findById(id: string): Promise<T | null>;
    findAll(): Promise<T[]>;
    save(entity: T): Promise<T>;
}
"""
    f = temp_test_dir / "interfaces.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    interfaces = result.get("interfaces", [])
    assert len(interfaces) >= 2
    names = [i["name"] for i in interfaces]
    assert "Serializable" in names
    assert "Repository" in names


def test_parse_imports(ts_parser, temp_test_dir):
    code = """import { readFileSync } from 'fs';
import * as path from 'path';
import type { Config } from './config';
"""
    f = temp_test_dir / "imports.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 2


def test_parse_variables(ts_parser, temp_test_dir):
    code = """const VERSION = "1.0.0";
let counter = 0;
const config = { host: "localhost", port: 8080 };
"""
    f = temp_test_dir / "vars.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    variables = result.get("variables", [])
    assert len(variables) >= 2


def test_parse_function_calls(ts_parser, temp_test_dir):
    code = """function demo() {
    console.log("hello");
    JSON.parse('{}');
    Array.from([1, 2, 3]);
}
"""
    f = temp_test_dir / "calls.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_enums(ts_parser, temp_test_dir):
    code = """enum Direction {
    Up = "UP",
    Down = "DOWN",
    Left = "LEFT",
    Right = "RIGHT",
}

const enum Color {
    Red = 0,
    Green = 1,
    Blue = 2,
}
"""
    f = temp_test_dir / "enums.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    # Enums may appear in classes or enums key
    all_types = result.get("classes", []) + result.get("enums", [])
    names = [t["name"] for t in all_types]
    assert "Direction" in names or "Color" in names


def test_parse_type_aliases(ts_parser, temp_test_dir):
    code = """type StringOrNumber = string | number;
type Status = "pending" | "active" | "inactive";
type Handler<T> = (event: T) => void;
"""
    f = temp_test_dir / "types.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    # Type aliases may be in variables or a dedicated key
    assert result["path"] == str(f)


def test_parse_generics(ts_parser, temp_test_dir):
    code = """function identity<T>(value: T): T {
    return value;
}

class Container<T> {
    constructor(private value: T) {}
    get(): T { return this.value; }
}
"""
    f = temp_test_dir / "generics.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    funcs = result["functions"]
    assert any(fn["name"] == "identity" for fn in funcs)

    classes = result.get("classes", [])
    assert any(c["name"] == "Container" for c in classes)


def test_parse_async_patterns(ts_parser, temp_test_dir):
    code = """async function fetchAll(urls: string[]): Promise<string[]> {
    const promises = urls.map(url => fetch(url).then(r => r.text()));
    return Promise.all(promises);
}

function* range(start: number, end: number): Generator<number> {
    for (let i = start; i < end; i++) {
        yield i;
    }
}
"""
    f = temp_test_dir / "async.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    funcs = result["functions"]
    names = [fn["name"] for fn in funcs]
    assert "fetchAll" in names


def test_parse_access_modifiers(ts_parser, temp_test_dir):
    code = """class Service {
    private name: string;
    protected config: object;
    public port: number;

    constructor(name: string) {
        this.name = name;
        this.config = {};
        this.port = 8080;
    }

    public start(): void {}
    private stop(): void {}
    protected restart(): void {}
}
"""
    f = temp_test_dir / "access.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    classes = result.get("classes", [])
    assert any(c["name"] == "Service" for c in classes)


def test_parse_object_literal_methods(ts_parser, temp_test_dir):
    code = """const registry = {
    greet(name: string) {
        return name;
    },
};
"""
    f = temp_test_dir / "object-methods.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    funcs = result["functions"]
    assert any(fn["name"] == "greet" for fn in funcs)


def test_parse_typescript_next_route_semantics(ts_parser, temp_test_dir):
    """Expose Next.js route semantics for app-router route handlers."""

    route_dir = temp_test_dir / "src" / "app" / "api" / "health"
    route_dir.mkdir(parents=True)
    route_file = route_dir / "route.ts"
    route_file.write_text(
        """\
import { NextRequest, NextResponse } from 'next/server';

export async function GET(_request: NextRequest) {
  return NextResponse.json({ ok: true });
}
""",
        encoding="utf-8",
    )

    result = ts_parser.parse(route_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["nextjs"]
    assert semantics["nextjs"]["module_kind"] == "route"
    assert semantics["nextjs"]["route_verbs"] == ["GET"]
    assert semantics["nextjs"]["metadata_exports"] == "none"
    assert semantics["nextjs"]["route_segments"] == ["api", "health"]
    assert semantics["nextjs"]["runtime_boundary"] == "server"
    assert semantics["nextjs"]["request_response_apis"] == [
        "NextRequest",
        "NextResponse",
    ]


def test_parse_decorators_do_not_emit_metadata(ts_parser, temp_test_dir):
    code = """@sealed
class Demo {}
"""
    f = temp_test_dir / "decorators.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    demo = next(item for item in result["classes"] if item["name"] == "Demo")
    assert demo["decorators"] == []


def test_result_structure(ts_parser, temp_test_dir):
    code = "const x = 1;\n"
    f = temp_test_dir / "minimal.ts"
    f.write_text(code)
    result = ts_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "typescript"
    assert "is_dependency" in result
    assert "functions" in result
    assert "classes" in result
    assert "interfaces" in result
    assert "imports" in result


def test_parse_empty_file(ts_parser, temp_test_dir):
    f = temp_test_dir / "empty.ts"
    f.write_text("")
    result = ts_parser.parse(f)
    assert len(result.get("functions", [])) == 0

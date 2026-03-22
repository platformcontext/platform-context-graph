"""Tests for the Go parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.go import GoTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def go_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("go"):
        pytest.skip("Go tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "go"
    wrapper.language = manager.get_language_safe("go")
    wrapper.parser = manager.create_parser("go")
    return GoTreeSitterParser(wrapper)


def test_parse_functions(go_parser, temp_test_dir):
    code = '''package main

import "fmt"

func Greet(name string) string {
    return fmt.Sprintf("Hello, %s!", name)
}

func Add(a, b int) int {
    return a + b
}

func Divide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, fmt.Errorf("division by zero")
    }
    return a / b, nil
}
'''
    f = temp_test_dir / "funcs.go"
    f.write_text(code)
    result = go_parser.parse(f)

    assert "functions" in result
    funcs = result["functions"]
    assert len(funcs) >= 3
    names = [fn["name"] for fn in funcs]
    assert "Greet" in names
    assert "Add" in names
    assert "Divide" in names


def test_parse_structs(go_parser, temp_test_dir):
    code = '''package main

type Point struct {
    X, Y float64
}

type Config struct {
    Host string
    Port int
}
'''
    f = temp_test_dir / "structs.go"
    f.write_text(code)
    result = go_parser.parse(f)

    classes = result.get("classes", [])
    assert len(classes) >= 2
    names = [c["name"] for c in classes]
    assert "Point" in names
    assert "Config" in names


def test_parse_interfaces(go_parser, temp_test_dir):
    code = '''package main

type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}

type Service interface {
    Start() error
    Stop() error
}
'''
    f = temp_test_dir / "ifaces.go"
    f.write_text(code)
    result = go_parser.parse(f)

    # Go interfaces may appear in classes or interfaces key
    interfaces = result.get("interfaces", result.get("classes", []))
    names = [i["name"] for i in interfaces]
    assert "Reader" in names or "Service" in names


def test_parse_methods(go_parser, temp_test_dir):
    code = '''package main

import "fmt"

type Point struct {
    X, Y float64
}

func (p Point) String() string {
    return fmt.Sprintf("(%g, %g)", p.X, p.Y)
}

func (p *Point) Translate(dx, dy float64) {
    p.X += dx
    p.Y += dy
}
'''
    f = temp_test_dir / "methods.go"
    f.write_text(code)
    result = go_parser.parse(f)

    funcs = result["functions"]
    names = [fn["name"] for fn in funcs]
    assert "String" in names or "Translate" in names


def test_parse_imports(go_parser, temp_test_dir):
    code = '''package main

import (
    "fmt"
    "os"
    "strings"
)
'''
    f = temp_test_dir / "imports.go"
    f.write_text(code)
    result = go_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 3


def test_parse_function_calls(go_parser, temp_test_dir):
    code = '''package main

import "fmt"

func main() {
    fmt.Println("hello")
    fmt.Sprintf("value: %d", 42)
}
'''
    f = temp_test_dir / "calls.go"
    f.write_text(code)
    result = go_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_generics(go_parser, temp_test_dir):
    code = '''package main

type Ordered interface {
    ~int | ~float64 | ~string
}

func Min[T Ordered](a, b T) T {
    if a < b {
        return a
    }
    return b
}

type Stack[T any] struct {
    items []T
}
'''
    f = temp_test_dir / "generics.go"
    f.write_text(code)
    result = go_parser.parse(f)

    funcs = result["functions"]
    names = [fn["name"] for fn in funcs]
    assert "Min" in names


def test_parse_package_vars(go_parser, temp_test_dir):
    code = '''package main

var (
    Version   = "1.0.0"
    BuildDate string
)

const (
    MaxRetries = 3
    Timeout    = 30
)
'''
    f = temp_test_dir / "vars.go"
    f.write_text(code)
    result = go_parser.parse(f)

    variables = result.get("variables", [])
    assert len(variables) >= 1


def test_result_structure(go_parser, temp_test_dir):
    code = 'package main\n'
    f = temp_test_dir / "minimal.go"
    f.write_text(code)
    result = go_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "go"
    assert "is_dependency" in result


def test_parse_empty_file(go_parser, temp_test_dir):
    f = temp_test_dir / "empty.go"
    f.write_text("package main\n")
    result = go_parser.parse(f)
    assert result["path"] == str(f)
    assert len(result.get("functions", [])) == 0


def test_parse_closures(go_parser, temp_test_dir):
    code = '''package main

func Counter() func() int {
    count := 0
    return func() int {
        count++
        return count
    }
}
'''
    f = temp_test_dir / "closures.go"
    f.write_text(code)
    result = go_parser.parse(f)
    funcs = result["functions"]
    assert any(fn["name"] == "Counter" for fn in funcs)

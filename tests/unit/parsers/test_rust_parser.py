"""Tests for the Rust parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.rust import RustTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def rust_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("rust"):
        pytest.skip("Rust tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "rust"
    wrapper.language = manager.get_language_safe("rust")
    wrapper.parser = manager.create_parser("rust")
    return RustTreeSitterParser(wrapper)


def test_parse_functions(rust_parser, temp_test_dir):
    code = """pub fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}

pub fn divide(a: f64, b: f64) -> Result<f64, String> {
    if b == 0.0 {
        Err("Division by zero".to_string())
    } else {
        Ok(a / b)
    }
}
"""
    f = temp_test_dir / "funcs.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    funcs = result["functions"]
    assert len(funcs) >= 3
    names = [fn["name"] for fn in funcs]
    assert "greet" in names
    assert "add" in names
    assert "divide" in names


def test_parse_structs(rust_parser, temp_test_dir):
    code = """pub struct Point {
    pub x: f64,
    pub y: f64,
}

pub struct Color(pub u8, pub u8, pub u8);
"""
    f = temp_test_dir / "structs.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Point" in names


def test_parse_enums(rust_parser, temp_test_dir):
    code = """pub enum Shape {
    Circle { radius: f64 },
    Rectangle { width: f64, height: f64 },
    Triangle(f64, f64, f64),
}

pub enum AppError {
    NotFound(String),
    Internal(Box<dyn std::error::Error>),
}
"""
    f = temp_test_dir / "enums.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Shape" in names or "AppError" in names


def test_parse_traits(rust_parser, temp_test_dir):
    code = """pub trait Describable {
    fn describe(&self) -> String;
}

pub trait Greetable {
    fn name(&self) -> &str;
    fn greet(&self) -> String {
        format!("Hello, {}!", self.name())
    }
}
"""
    f = temp_test_dir / "traits.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    traits = result.get("traits", [])
    assert len(traits) >= 2
    names = [t["name"] for t in traits]
    assert "Describable" in names
    assert "Greetable" in names


def test_parse_imports(rust_parser, temp_test_dir):
    code = """use std::fmt;
use std::collections::HashMap;
use crate::models::User;
"""
    f = temp_test_dir / "imports.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 3


def test_parse_function_calls(rust_parser, temp_test_dir):
    code = """fn main() {
    let s = String::from("hello");
    println!("{}", s);
    let v = vec![1, 2, 3];
    v.len();
}
"""
    f = temp_test_dir / "calls.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_impl_block(rust_parser, temp_test_dir):
    code = """struct Point {
    x: f64,
    y: f64,
}

impl Point {
    fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }

    fn distance(&self, other: &Point) -> f64 {
        ((self.x - other.x).powi(2) + (self.y - other.y).powi(2)).sqrt()
    }
}
"""
    f = temp_test_dir / "impl.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    funcs = result["functions"]
    names = [fn["name"] for fn in funcs]
    assert "new" in names or "distance" in names


def test_parse_generics(rust_parser, temp_test_dir):
    code = """pub fn largest<T: PartialOrd>(items: &[T]) -> Option<&T> {
    items.iter().reduce(|a, b| if a >= b { a } else { b })
}

pub struct Wrapper<T> {
    value: T,
}
"""
    f = temp_test_dir / "generics.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    funcs = result["functions"]
    assert any(fn["name"] == "largest" for fn in funcs)


def test_parse_lifetimes(rust_parser, temp_test_dir):
    code = """pub fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

pub struct Excerpt<'a> {
    pub text: &'a str,
}
"""
    f = temp_test_dir / "lifetimes.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    funcs = result["functions"]
    assert any(fn["name"] == "longest" for fn in funcs)


def test_result_structure(rust_parser, temp_test_dir):
    code = "fn placeholder() {}\n"
    f = temp_test_dir / "minimal.rs"
    f.write_text(code)
    result = rust_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "rust"
    assert "is_dependency" in result
    assert "functions" in result
    assert "classes" in result
    assert "traits" in result
    assert "imports" in result
    assert "function_calls" in result


def test_parse_empty_file(rust_parser, temp_test_dir):
    f = temp_test_dir / "empty.rs"
    f.write_text("")
    result = rust_parser.parse(f)
    assert len(result.get("functions", [])) == 0

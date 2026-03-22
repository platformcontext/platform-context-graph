"""Tests for the C++ parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.cpp import CppTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def cpp_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("cpp"):
        pytest.skip("C++ tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "cpp"
    wrapper.language = manager.get_language_safe("cpp")
    wrapper.parser = manager.create_parser("cpp")
    return CppTreeSitterParser(wrapper)


def test_parse_functions(cpp_parser, temp_test_dir):
    code = """#include <string>

std::string greet(const std::string& name) {
    return "Hello, " + name + "!";
}

int add(int a, int b) {
    return a + b;
}
"""
    f = temp_test_dir / "funcs.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    funcs = result["functions"]
    assert len(funcs) >= 2
    names = [fn["name"] for fn in funcs]
    assert "greet" in names
    assert "add" in names


def test_parse_classes(cpp_parser, temp_test_dir):
    code = """class Shape {
public:
    virtual ~Shape() = default;
    virtual double area() const = 0;
};

class Circle : public Shape {
public:
    Circle(double r) : radius_(r) {}
    double area() const override { return 3.14 * radius_ * radius_; }
private:
    double radius_;
};
"""
    f = temp_test_dir / "classes.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Shape" in names
    assert "Circle" in names


def test_parse_class_methods(cpp_parser, temp_test_dir):
    code = """#include <string>

class Greeter {
public:
    std::string greet(const std::string& name) {
        return "Hello, " + name;
    }
};

// Out-of-class method definition
std::string Greeter::greet(const std::string& name) {
    return "Hello, " + name;
}
"""
    f = temp_test_dir / "methods.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    funcs = result["functions"]
    assert len(funcs) >= 1


def test_parse_structs(cpp_parser, temp_test_dir):
    code = """struct Point {
    double x;
    double y;
};

struct Config {
    std::string host;
    int port;
};
"""
    f = temp_test_dir / "structs.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    structs = result.get("structs", [])
    names = [s["name"] for s in structs]
    assert "Point" in names
    assert "Config" in names


def test_parse_enums(cpp_parser, temp_test_dir):
    code = """enum OldColor { RED, GREEN, BLUE };

enum class Direction {
    North,
    South,
    East,
    West
};

enum class HttpStatus : int {
    OK = 200,
    NotFound = 404
};
"""
    f = temp_test_dir / "enums.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    enums = result.get("enums", [])
    assert len(enums) >= 2


def test_parse_unions(cpp_parser, temp_test_dir):
    code = """union DataValue {
    int intVal;
    float floatVal;
    char charVal;
};
"""
    f = temp_test_dir / "unions.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    unions = result.get("unions", [])
    assert len(unions) >= 1
    assert unions[0]["name"] == "DataValue"


def test_parse_includes(cpp_parser, temp_test_dir):
    code = """#include <iostream>
#include <vector>
#include <string>
#include "shapes.h"
"""
    f = temp_test_dir / "includes.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 4


def test_parse_function_calls(cpp_parser, temp_test_dir):
    code = """#include <iostream>
#include <vector>

void demo() {
    std::cout << "hello" << std::endl;
    std::vector<int> v;
    v.push_back(1);
    v.size();
}
"""
    f = temp_test_dir / "calls.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_macros(cpp_parser, temp_test_dir):
    code = """#define MAX_SIZE 1024
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define VERSION "1.0.0"
"""
    f = temp_test_dir / "macros.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    macros = result.get("macros", [])
    assert len(macros) >= 2


def test_parse_templates(cpp_parser, temp_test_dir):
    code = """template<typename T>
T max_value(T a, T b) {
    return (a > b) ? a : b;
}

template<typename T>
class Stack {
    void push(const T& item);
};
"""
    f = temp_test_dir / "templates.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    funcs = result["functions"]
    assert any(fn["name"] == "max_value" for fn in funcs)


def test_parse_lambdas(cpp_parser, temp_test_dir):
    code = """#include <functional>

void demo() {
    auto greet = []() { return "hello"; };
    auto add = [](int a, int b) { return a + b; };
    int factor = 3;
    auto multiply = [factor](int x) { return x * factor; };
    greet();
    add(1, 2);
}
"""
    f = temp_test_dir / "lambdas.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    funcs = result["functions"]
    assert any(fn["name"] == "demo" for fn in funcs)


def test_parse_smart_ptrs(cpp_parser, temp_test_dir):
    code = """#include <memory>

class Resource {
public:
    void use() const {}
};

void demo() {
    auto p = std::make_unique<Resource>();
    p->use();
    auto s = std::make_shared<Resource>();
    s->use();
}
"""
    f = temp_test_dir / "smartptrs.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_variables_and_fields(cpp_parser, temp_test_dir):
    code = """class Counter {
public:
    int current = 0;
};

void demo() {
    int total = 1;
}
"""
    f = temp_test_dir / "variables.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    variables = result.get("variables", [])
    assert any(item["name"] == "current" for item in variables)
    assert any(item["name"] == "total" for item in variables)


def test_result_structure(cpp_parser, temp_test_dir):
    code = "void placeholder() {}\n"
    f = temp_test_dir / "minimal.cpp"
    f.write_text(code)
    result = cpp_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "cpp"
    assert "is_dependency" in result
    assert "functions" in result
    assert "classes" in result
    assert "structs" in result
    assert "enums" in result


def test_parse_empty_file(cpp_parser, temp_test_dir):
    f = temp_test_dir / "empty.cpp"
    f.write_text("")
    result = cpp_parser.parse(f)
    assert len(result.get("functions", [])) == 0

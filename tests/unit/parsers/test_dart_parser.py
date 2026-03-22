"""Tests for the Dart parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.dart import DartTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def dart_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("dart"):
        pytest.skip("Dart tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "dart"
    wrapper.language = manager.get_language_safe("dart")
    wrapper.parser = manager.create_parser("dart")
    return DartTreeSitterParser(wrapper)


def test_parse_functions(dart_parser, temp_test_dir):
    code = r"""String greet(String name) => 'Hello, $name!';

int add(int a, int b) => a + b;

double? divide(double a, double b) {
  if (b == 0) return null;
  return a / b;
}
"""
    f = temp_test_dir / "funcs.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    funcs = result.get("functions", [])
    assert len(funcs) >= 2
    names = [fn["name"] for fn in funcs]
    assert "greet" in names or "add" in names


def test_parse_classes(dart_parser, temp_test_dir):
    code = r"""abstract class Shape {
  double get area;
  double get perimeter;
}

class Circle extends Shape {
  final double radius;
  Circle(this.radius);

  @override
  double get area => 3.14 * radius * radius;

  @override
  double get perimeter => 2 * 3.14 * radius;
}

class Person {
  final String name;
  final int age;
  Person(this.name, this.age);
  String greet() => 'Hi, I am $name';
}
"""
    f = temp_test_dir / "classes.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    classes = result.get("classes", [])
    assert len(classes) >= 2
    names = [c["name"] for c in classes]
    assert "Shape" in names or "Circle" in names


def test_parse_mixins(dart_parser, temp_test_dir):
    code = r"""mixin Loggable {
  void log(String message) {
    print('[$runtimeType] $message');
  }
}

class Service with Loggable {
  final String name;
  Service(this.name);

  void start() {
    log('Starting $name');
  }
}
"""
    f = temp_test_dir / "mixins.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Loggable" in names or "Service" in names


def test_parse_extensions(dart_parser, temp_test_dir):
    code = r"""extension StringTools on String {
  String shout() => toUpperCase();
}
"""
    f = temp_test_dir / "extensions.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "StringTools" in names


def test_parse_enums(dart_parser, temp_test_dir):
    code = """enum Color {
  red,
  green,
  blue;
}

enum Status {
  active,
  inactive;

  bool get isTerminal => this == Status.inactive;
}
"""
    f = temp_test_dir / "enums.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    # Enums may be in classes or enums key
    all_types = result.get("classes", []) + result.get("enums", [])
    names = [t["name"] for t in all_types]
    assert "Color" in names or "Status" in names


def test_parse_imports(dart_parser, temp_test_dir):
    code = """import 'dart:async';
import 'dart:io';
import 'package:http/http.dart' as http;
"""
    f = temp_test_dir / "imports.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 2


def test_parse_exports(dart_parser, temp_test_dir):
    code = "export 'foo.dart';\n"
    f = temp_test_dir / "exports.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    imports = result.get("imports", [])
    assert any(item["name"] == "foo.dart" for item in imports)


def test_parse_variables(dart_parser, temp_test_dir):
    code = """const String version = '1.0.0';
final int maxRetries = 3;
var counter = 0;
"""
    f = temp_test_dir / "vars.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    variables = result.get("variables", [])
    assert len(variables) >= 1


def test_parse_function_calls(dart_parser, temp_test_dir):
    code = """void demo() {
  print('hello');
  var list = [1, 2, 3];
  list.map((x) => x * 2);
  list.where((x) => x > 1);
}
"""
    f = temp_test_dir / "calls.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_result_structure(dart_parser, temp_test_dir):
    code = "void main() {}\n"
    f = temp_test_dir / "minimal.dart"
    f.write_text(code)
    result = dart_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "dart"
    assert "is_dependency" in result


def test_parse_empty_file(dart_parser, temp_test_dir):
    f = temp_test_dir / "empty.dart"
    f.write_text("")
    result = dart_parser.parse(f)
    assert len(result.get("functions", [])) == 0

"""Tests for the Scala parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.scala import ScalaTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def scala_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("scala"):
        pytest.skip("Scala tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "scala"
    wrapper.language = manager.get_language_safe("scala")
    wrapper.parser = manager.create_parser("scala")
    return ScalaTreeSitterParser(wrapper)


def test_parse_object(scala_parser, temp_test_dir):
    code = '''object Main extends App {
  val version = "1.0.0"
  def formatVersion: String = s"v$version"
}
'''
    f = temp_test_dir / "Main.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Main" in names


def test_parse_classes(scala_parser, temp_test_dir):
    code = '''class Person(val name: String, val age: Int) {
  def greet(): String = s"Hello, I'm $name"
}

case class Point(x: Double, y: Double) {
  def distance(other: Point): Double = {
    val dx = x - other.x
    val dy = y - other.y
    math.sqrt(dx * dx + dy * dy)
  }
}
'''
    f = temp_test_dir / "classes.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Person" in names or "Point" in names


def test_parse_traits(scala_parser, temp_test_dir):
    code = '''sealed trait Shape {
  def area: Double
  def perimeter: Double
}

trait Describable {
  def describe: String
}
'''
    f = temp_test_dir / "traits.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    traits = result.get("traits", result.get("classes", []))
    names = [t["name"] for t in traits]
    assert "Shape" in names or "Describable" in names


def test_parse_functions(scala_parser, temp_test_dir):
    code = '''object Functional {
  def transform[A, B](items: List[A])(f: A => B): List[B] = items.map(f)
  def filter[A](items: List[A])(p: A => Boolean): List[A] = items.filter(p)
  def multiply(a: Int)(b: Int): Int = a * b
}
'''
    f = temp_test_dir / "funcs.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    funcs = result.get("functions", [])
    names = [fn["name"] for fn in funcs]
    assert "transform" in names or "filter" in names or "multiply" in names


def test_parse_imports(scala_parser, temp_test_dir):
    code = '''import scala.collection.mutable
import java.util.{List, ArrayList}
import scala.math._
'''
    f = temp_test_dir / "imports.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 2


def test_parse_variables(scala_parser, temp_test_dir):
    code = '''object Config {
  val version: String = "1.0.0"
  var debug: Boolean = false
  lazy val data: List[Int] = List(1, 2, 3)
}
'''
    f = temp_test_dir / "vars.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    variables = result.get("variables", [])
    assert len(variables) >= 1


def test_parse_function_calls(scala_parser, temp_test_dir):
    code = '''object Demo {
  def run(): Unit = {
    println("hello")
    List(1, 2, 3).map(_ * 2).filter(_ > 2)
  }
}
'''
    f = temp_test_dir / "calls.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_abstract_class(scala_parser, temp_test_dir):
    code = '''abstract class Service(val name: String) {
  def start(): Unit
  def stop(): Unit
  def isRunning: Boolean
}
'''
    f = temp_test_dir / "abstract.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Service" in names


def test_parse_companion_object(scala_parser, temp_test_dir):
    code = '''class Person(val name: String)

object Person {
  def apply(name: String): Person = new Person(name)
}
'''
    f = temp_test_dir / "companion.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Person" in names


def test_result_structure(scala_parser, temp_test_dir):
    code = 'object Minimal\n'
    f = temp_test_dir / "minimal.scala"
    f.write_text(code)
    result = scala_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "scala"
    assert "is_dependency" in result


def test_parse_empty_file(scala_parser, temp_test_dir):
    f = temp_test_dir / "empty.scala"
    f.write_text("")
    result = scala_parser.parse(f)
    assert len(result.get("functions", [])) == 0

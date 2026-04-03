"""Tests for the Java parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.java import JavaTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def java_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("java"):
        pytest.skip("Java tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "java"
    wrapper.language = manager.get_language_safe("java")
    wrapper.parser = manager.create_parser("java")
    return JavaTreeSitterParser(wrapper)


def test_parse_class(java_parser, temp_test_dir):
    code = """public class Person {
    private String name;
    private int age;

    public Person(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public String greet() {
        return "Hello, " + name;
    }
}
"""
    f = temp_test_dir / "Person.java"
    f.write_text(code)
    result = java_parser.parse(f)

    classes = result.get("classes", [])
    assert len(classes) >= 1
    assert any(c["name"] == "Person" for c in classes)


def test_parse_methods(java_parser, temp_test_dir):
    code = """public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }

    public static int multiply(int a, int b) {
        return a * b;
    }

    private void log(String message) {
        System.out.println(message);
    }
}
"""
    f = temp_test_dir / "Calculator.java"
    f.write_text(code)
    result = java_parser.parse(f)

    funcs = result.get("functions", [])
    names = [fn["name"] for fn in funcs]
    assert "add" in names or "multiply" in names


def test_parse_interface(java_parser, temp_test_dir):
    code = """public interface Greetable {
    String getGreeting();

    default String greetLoudly() {
        return getGreeting().toUpperCase();
    }
}
"""
    f = temp_test_dir / "Greetable.java"
    f.write_text(code)
    result = java_parser.parse(f)

    interfaces = result.get("interfaces", result.get("classes", []))
    names = [i["name"] for i in interfaces]
    assert "Greetable" in names


def test_parse_inheritance(java_parser, temp_test_dir):
    code = """public class Animal {
    protected String name;
    public Animal(String name) { this.name = name; }
}

class Dog extends Animal {
    public Dog(String name) { super(name); }
    public String bark() { return "Woof!"; }
}
"""
    f = temp_test_dir / "Inheritance.java"
    f.write_text(code)
    result = java_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Animal" in names
    assert "Dog" in names


def test_parse_enum(java_parser, temp_test_dir):
    code = """public enum Color {
    RED(255, 0, 0),
    GREEN(0, 255, 0),
    BLUE(0, 0, 255);

    private final int r, g, b;
    Color(int r, int g, int b) { this.r = r; this.g = g; this.b = b; }
    public String hex() { return String.format("#%02x%02x%02x", r, g, b); }
}
"""
    f = temp_test_dir / "Color.java"
    f.write_text(code)
    result = java_parser.parse(f)

    # Enums may appear in classes or enums key
    all_types = result.get("classes", []) + result.get("enums", [])
    names = [c["name"] for c in all_types]
    assert "Color" in names


def test_parse_imports(java_parser, temp_test_dir):
    code = """import java.util.List;
import java.util.ArrayList;
import java.util.stream.Collectors;

public class Main {
    public static void main(String[] args) {}
}
"""
    f = temp_test_dir / "Main.java"
    f.write_text(code)
    result = java_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 3


def test_parse_annotations(java_parser, temp_test_dir):
    code = """import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Logged {
    String value() default "";
}
"""
    f = temp_test_dir / "Logged.java"
    f.write_text(code)
    result = java_parser.parse(f)

    annotations = result.get("annotations", result.get("classes", []))
    names = [a["name"] for a in annotations]
    assert "Logged" in names


def test_parse_generics(java_parser, temp_test_dir):
    code = """import java.util.*;

public class Container<T> {
    private List<T> items = new ArrayList<>();

    public void add(T item) {
        items.add(item);
    }

    public T get(int index) {
        return items.get(index);
    }
}
"""
    f = temp_test_dir / "Container.java"
    f.write_text(code)
    result = java_parser.parse(f)

    classes = result.get("classes", [])
    assert any(c["name"] == "Container" for c in classes)


def test_parse_inner_classes(java_parser, temp_test_dir):
    code = """public class Outer {
    private int value = 10;

    public class Inner {
        public int getValue() { return value; }
    }

    public static class StaticNested {
        public String describe() { return "nested"; }
    }
}
"""
    f = temp_test_dir / "Outer.java"
    f.write_text(code)
    result = java_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Outer" in names


def test_parse_function_calls(java_parser, temp_test_dir):
    code = """public class App {
    public void run() {
        System.out.println("hello");
        String.format("value: %d", 42);
        process();
    }
    private void process() {}
}
"""
    f = temp_test_dir / "App.java"
    f.write_text(code)
    result = java_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_variables_and_fields(java_parser, temp_test_dir):
    code = """public class Counter {
    private int current = 0;

    public void increment() {
        int next = current + 1;
        current = next;
    }
}
"""
    f = temp_test_dir / "Counter.java"
    f.write_text(code)
    result = java_parser.parse(f)

    variables = result.get("variables", [])
    assert any(item["name"] == "current" for item in variables)
    assert any(item["name"] == "next" for item in variables)


def test_parse_object_creation_calls(java_parser, temp_test_dir):
    code = """public class Builder {
    public void run() {
        StringBuilder builder = new StringBuilder();
        builder.append("hi");
    }
}
"""
    f = temp_test_dir / "Builder.java"
    f.write_text(code)
    result = java_parser.parse(f)

    calls = result.get("function_calls", [])
    assert any(item["name"] == "StringBuilder" for item in calls)


def test_result_structure(java_parser, temp_test_dir):
    code = "public class Minimal {}\n"
    f = temp_test_dir / "Minimal.java"
    f.write_text(code)
    result = java_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "java"
    assert "is_dependency" in result


def test_parse_empty_class(java_parser, temp_test_dir):
    code = "public class Empty {}\n"
    f = temp_test_dir / "Empty.java"
    f.write_text(code)
    result = java_parser.parse(f)
    assert len(result.get("functions", [])) == 0

"""Tests for the C# parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.csharp import CSharpTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def csharp_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("c_sharp"):
        pytest.skip("C# tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "c_sharp"
    wrapper.language = manager.get_language_safe("c_sharp")
    wrapper.parser = manager.create_parser("c_sharp")
    return CSharpTreeSitterParser(wrapper)


def test_parse_class(csharp_parser, temp_test_dir):
    code = """namespace Test {
    public class Person {
        public string Name { get; }
        public int Age { get; }

        public Person(string name, int age) {
            Name = name;
            Age = age;
        }

        public string Greet() {
            return $"Hi, I\'m {Name}";
        }
    }
}
"""
    f = temp_test_dir / "Person.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    classes = result.get("classes", [])
    assert len(classes) >= 1
    assert any(c["name"] == "Person" for c in classes)


def test_parse_inheritance(csharp_parser, temp_test_dir):
    code = """public class Animal {
    public string Name { get; }
    public Animal(string name) { Name = name; }
    public virtual string Speak() { return "..."; }
}

public class Dog : Animal {
    public Dog(string name) : base(name) {}
    public override string Speak() { return "Woof!"; }
}
"""
    f = temp_test_dir / "Animals.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Animal" in names
    assert "Dog" in names


def test_parse_interface(csharp_parser, temp_test_dir):
    code = """public interface IService {
    string Execute(string input);
    bool IsReady { get; }
}

public interface IRepository<T> where T : class {
    T FindById(string id);
}
"""
    f = temp_test_dir / "IService.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    interfaces = result.get("interfaces", result.get("classes", []))
    names = [i["name"] for i in interfaces]
    assert "IService" in names


def test_parse_methods(csharp_parser, temp_test_dir):
    code = """public class Calculator {
    public int Add(int a, int b) { return a + b; }
    public static int Multiply(int a, int b) { return a * b; }
    private void Log(string msg) { Console.WriteLine(msg); }
}
"""
    f = temp_test_dir / "Calculator.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    funcs = result.get("functions", [])
    names = [fn["name"] for fn in funcs]
    assert "Add" in names or "Multiply" in names


def test_parse_record(csharp_parser, temp_test_dir):
    code = """public record Point(double X, double Y) {
    public double DistanceTo(Point other) {
        return Math.Sqrt(Math.Pow(X - other.X, 2) + Math.Pow(Y - other.Y, 2));
    }
}
"""
    f = temp_test_dir / "Point.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    records = result.get("records", result.get("classes", []))
    names = [r["name"] for r in records]
    assert "Point" in names


def test_parse_enum(csharp_parser, temp_test_dir):
    code = """public enum Status {
    Active,
    Inactive,
    Pending,
    Deleted
}

[Flags]
public enum Permissions {
    None = 0,
    Read = 1,
    Write = 2,
    Execute = 4,
    All = Read | Write | Execute
}
"""
    f = temp_test_dir / "Enums.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    enums = result.get("enums", result.get("classes", []))
    names = [e["name"] for e in enums]
    assert "Status" in names or "Permissions" in names


def test_parse_imports(csharp_parser, temp_test_dir):
    code = """using System;
using System.Collections.Generic;
using System.Linq;

public class Demo {
    public void Run() {}
}
"""
    f = temp_test_dir / "Demo.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 3


def test_parse_generics(csharp_parser, temp_test_dir):
    code = """public class Repository<T> where T : class {
    private readonly Dictionary<string, T> store = new();

    public T FindById(string id) { return store[id]; }
    public void Save(T entity) { store["id"] = entity; }
}
"""
    f = temp_test_dir / "Repository.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    classes = result.get("classes", [])
    assert any(c["name"] == "Repository" for c in classes)


def test_parse_struct(csharp_parser, temp_test_dir):
    code = """public struct Color {
    public byte R;
    public byte G;
    public byte B;

    public Color(byte r, byte g, byte b) { R = r; G = g; B = b; }
}
"""
    f = temp_test_dir / "Color.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    structs = result.get("structs", result.get("classes", []))
    names = [s["name"] for s in structs]
    assert "Color" in names


def test_parse_properties_and_object_creation(csharp_parser, temp_test_dir):
    code = """using System;

public class Service {
    public string Name { get; set; } = "default";
}

public class Runner {
    public void Execute() {
        var service = new Service();
        Console.WriteLine(service.Name);
    }
}
"""
    f = temp_test_dir / "Runner.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    properties = result.get("properties", [])
    calls = result.get("function_calls", [])
    assert any(item["name"] == "Name" for item in properties)
    assert any(item["name"] == "Service" for item in calls)


def test_parse_local_functions(csharp_parser, temp_test_dir):
    code = """public class Demo {
    public void Run() {
        int Local(int value) { return value + 1; }
        Local(1);
    }
}
"""
    f = temp_test_dir / "LocalFunctions.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    functions = result.get("functions", [])
    assert any(item["name"] == "Local" for item in functions)


def test_result_structure(csharp_parser, temp_test_dir):
    code = "public class Minimal {}\n"
    f = temp_test_dir / "Minimal.cs"
    f.write_text(code)
    result = csharp_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "c_sharp"
    assert "is_dependency" in result


def test_parse_empty_file(csharp_parser, temp_test_dir):
    f = temp_test_dir / "Empty.cs"
    f.write_text("")
    result = csharp_parser.parse(f)
    assert len(result.get("functions", [])) == 0

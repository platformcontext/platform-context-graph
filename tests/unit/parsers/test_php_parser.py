"""Tests for the PHP parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.php import PhpTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def php_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("php"):
        pytest.skip("PHP tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "php"
    wrapper.language = manager.get_language_safe("php")
    wrapper.parser = manager.create_parser("php")
    return PhpTreeSitterParser(wrapper)


def test_parse_functions(php_parser, temp_test_dir):
    code = '''<?php
function greet(string $name): string {
    return "Hello, {$name}!";
}

function add(int $a, int $b): int {
    return $a + $b;
}
'''
    f = temp_test_dir / "funcs.php"
    f.write_text(code)
    result = php_parser.parse(f)

    funcs = result["functions"]
    assert len(funcs) >= 2
    names = [fn["name"] for fn in funcs]
    assert "greet" in names
    assert "add" in names


def test_parse_classes(php_parser, temp_test_dir):
    code = '''<?php
class Person {
    private string $name;

    public function __construct(string $name) {
        $this->name = $name;
    }

    public function greet(): string {
        return "Hello, {$this->name}";
    }
}

abstract class Shape {
    abstract public function area(): float;
}
'''
    f = temp_test_dir / "classes.php"
    f.write_text(code)
    result = php_parser.parse(f)

    classes = result.get("classes", [])
    assert len(classes) >= 2
    names = [c["name"] for c in classes]
    assert "Person" in names
    assert "Shape" in names


def test_parse_interfaces(php_parser, temp_test_dir):
    code = '''<?php
interface Identifiable {
    public function getId(): string;
}

interface Repository {
    public function findById(string $id): ?object;
    public function findAll(): array;
}
'''
    f = temp_test_dir / "interfaces.php"
    f.write_text(code)
    result = php_parser.parse(f)

    interfaces = result.get("interfaces", [])
    names = [i["name"] for i in interfaces]
    assert "Identifiable" in names
    assert "Repository" in names


def test_parse_traits(php_parser, temp_test_dir):
    code = '''<?php
trait Loggable {
    public function log(string $message): void {
        echo "[LOG] {$message}\\n";
    }
}

trait Serializable {
    public function toJson(): string {
        return json_encode(get_object_vars($this));
    }
}
'''
    f = temp_test_dir / "traits.php"
    f.write_text(code)
    result = php_parser.parse(f)

    traits = result.get("traits", [])
    names = [t["name"] for t in traits]
    assert "Loggable" in names
    assert "Serializable" in names


def test_parse_imports(php_parser, temp_test_dir):
    code = '''<?php
use App\\Models\\User;
use App\\Services\\{AuthService, MailService};
use Illuminate\\Support\\Facades\\DB;
'''
    f = temp_test_dir / "imports.php"
    f.write_text(code)
    result = php_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 2


def test_parse_function_calls(php_parser, temp_test_dir):
    code = '''<?php
function demo() {
    echo "hello";
    strlen("test");
    array_map(fn($x) => $x * 2, [1, 2, 3]);
}
'''
    f = temp_test_dir / "calls.php"
    f.write_text(code)
    result = php_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_inheritance(php_parser, temp_test_dir):
    code = '''<?php
class Animal {
    public function speak(): string { return "..."; }
}

class Dog extends Animal {
    public function speak(): string { return "Woof!"; }
}
'''
    f = temp_test_dir / "inheritance.php"
    f.write_text(code)
    result = php_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Animal" in names
    assert "Dog" in names


def test_result_structure(php_parser, temp_test_dir):
    code = '<?php\nfunction placeholder() {}\n'
    f = temp_test_dir / "minimal.php"
    f.write_text(code)
    result = php_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "php"
    assert "is_dependency" in result


def test_parse_empty_file(php_parser, temp_test_dir):
    f = temp_test_dir / "empty.php"
    f.write_text("<?php\n")
    result = php_parser.parse(f)
    assert len(result.get("functions", [])) == 0

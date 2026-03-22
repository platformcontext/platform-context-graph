"""Tests for the C parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.c import CTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def c_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("c"):
        pytest.skip("C tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "c"
    wrapper.language = manager.get_language_safe("c")
    wrapper.parser = manager.create_parser("c")
    return CTreeSitterParser(wrapper)


def test_parse_functions(c_parser, temp_test_dir):
    code = """#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

void greet(const char* name) {
    printf("Hello, %s!\\n", name);
}

double divide(double a, double b) {
    if (b == 0.0) return 0.0;
    return a / b;
}
"""
    f = temp_test_dir / "funcs.c"
    f.write_text(code)
    result = c_parser.parse(f)

    funcs = result["functions"]
    assert len(funcs) >= 3
    names = [fn["name"] for fn in funcs]
    assert "add" in names
    assert "greet" in names
    assert "divide" in names


def test_parse_structs(c_parser, temp_test_dir):
    code = """struct Point {
    double x;
    double y;
};

struct Config {
    char host[256];
    int port;
};
"""
    f = temp_test_dir / "structs.c"
    f.write_text(code)
    result = c_parser.parse(f)

    structs = result.get("structs", result.get("classes", []))
    names = [s["name"] for s in structs]
    assert "Point" in names


def test_parse_enums(c_parser, temp_test_dir):
    code = """enum StatusCode {
    STATUS_OK = 0,
    STATUS_ERROR = 1,
    STATUS_NOT_FOUND = 2
};
"""
    f = temp_test_dir / "enums.c"
    f.write_text(code)
    result = c_parser.parse(f)

    enums = result.get("enums", result.get("classes", []))
    assert len(enums) >= 1


def test_parse_unions(c_parser, temp_test_dir):
    code = """union GenericValue {
    int intVal;
    float floatVal;
    char strVal[64];
};
"""
    f = temp_test_dir / "unions.c"
    f.write_text(code)
    result = c_parser.parse(f)

    unions = result.get("unions", result.get("classes", []))
    assert len(unions) >= 1


def test_parse_typedefs(c_parser, temp_test_dir):
    code = """typedef int (*TransformFn)(int);
typedef void (*CallbackFn)(const char* message);

typedef struct {
    int x;
    int y;
} Point2D;
"""
    f = temp_test_dir / "typedefs.c"
    f.write_text(code)
    result = c_parser.parse(f)
    # Typedefs may appear in various result keys
    assert result["path"] == str(f)


def test_parse_typedefs_do_not_emit_dedicated_entities(c_parser, temp_test_dir):
    code = """typedef int my_int;\n"""
    f = temp_test_dir / "typedef_alias.c"
    f.write_text(code)
    result = c_parser.parse(f)

    assert result.get("classes", []) == []
    assert result.get("variables", []) == []


def test_parse_includes(c_parser, temp_test_dir):
    code = """#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "types.h"
"""
    f = temp_test_dir / "includes.c"
    f.write_text(code)
    result = c_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 4


def test_parse_function_calls(c_parser, temp_test_dir):
    code = """#include <stdio.h>

void demo() {
    printf("hello\\n");
    malloc(1024);
    free(NULL);
}
"""
    f = temp_test_dir / "calls.c"
    f.write_text(code)
    result = c_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_macros(c_parser, temp_test_dir):
    code = """#define MAX_SIZE 1024
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define CLAMP(x, lo, hi) ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))
"""
    f = temp_test_dir / "macros.c"
    f.write_text(code)
    result = c_parser.parse(f)

    macros = result.get("macros", [])
    assert len(macros) >= 2


def test_parse_function_pointers(c_parser, temp_test_dir):
    code = """int apply_transform(int value, int (*transform)(int)) {
    return transform(value);
}

int square(int x) { return x * x; }
int negate(int x) { return -x; }
"""
    f = temp_test_dir / "fnptrs.c"
    f.write_text(code)
    result = c_parser.parse(f)

    funcs = result["functions"]
    names = [fn["name"] for fn in funcs]
    assert "apply_transform" in names
    assert "square" in names


def test_parse_initialized_variables(c_parser, temp_test_dir):
    code = """int compute(void) {
    int total = 42;
    return total;
}
"""
    f = temp_test_dir / "variables.c"
    f.write_text(code)
    result = c_parser.parse(f)

    variables = result.get("variables", [])
    assert any(item["name"] == "total" for item in variables)


def test_result_structure(c_parser, temp_test_dir):
    code = "void placeholder(void) {}\n"
    f = temp_test_dir / "minimal.c"
    f.write_text(code)
    result = c_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "c"
    assert "is_dependency" in result


def test_parse_empty_file(c_parser, temp_test_dir):
    f = temp_test_dir / "empty.c"
    f.write_text("")
    result = c_parser.parse(f)
    assert len(result.get("functions", [])) == 0

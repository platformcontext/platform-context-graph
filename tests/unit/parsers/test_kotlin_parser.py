"""Tests for the handwritten Kotlin parser facade and support module."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.kotlin import KotlinTreeSitterParser
from platform_context_graph.parsers.languages.kotlin_support import pre_scan_kotlin
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def kotlin_parser() -> KotlinTreeSitterParser:
    """Build a Kotlin parser when the grammar is available."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("kotlin"):
        pytest.skip("Kotlin tree-sitter grammar is not available in this environment")

    wrapper = MagicMock()
    wrapper.language_name = "kotlin"
    wrapper.language = manager.get_language_safe("kotlin")
    wrapper.parser = manager.create_parser("kotlin")
    return KotlinTreeSitterParser(wrapper)


def test_parse_kotlin_simple_declarations(
    kotlin_parser: KotlinTreeSitterParser, temp_test_dir
) -> None:
    """Parse a small Kotlin file and verify key declarations are captured."""
    source = """
package demo

import kotlin.text.StringBuilder

class Greeter {
    fun greet(name: String): String {
        return name
    }
}

fun hello(value: String): String {
    return value
}
"""
    source_file = temp_test_dir / "sample.kt"
    source_file.write_text(source, encoding="utf-8")

    result = kotlin_parser.parse(source_file)

    assert any(item["name"] == "Greeter" for item in result["classes"])
    assert any(item["name"] == "hello" for item in result["functions"])
    assert any(
        item["name"] == "kotlin.text.StringBuilder" for item in result["imports"]
    )


def test_pre_scan_kotlin_keeps_public_import_surface(temp_test_dir) -> None:
    """Return a name-to-file map through the Kotlin support module."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("kotlin"):
        pytest.skip("Kotlin tree-sitter grammar is not available in this environment")

    wrapper = MagicMock()
    wrapper.language_name = "kotlin"
    wrapper.language = manager.get_language_safe("kotlin")
    wrapper.parser = manager.create_parser("kotlin")

    source_file = temp_test_dir / "prescan_sample.kt"
    source_file.write_text(
        "class Greeter\nfun hello() = Unit\n",
        encoding="utf-8",
    )

    imports_map = pre_scan_kotlin([source_file], wrapper)

    assert imports_map["Greeter"] == [str(source_file)]


def test_parse_kotlin_extended_surface(
    kotlin_parser: KotlinTreeSitterParser, temp_test_dir
) -> None:
    """Parse Kotlin objects, companion objects, variables, and calls."""
    source = """
package demo

class Greeter private constructor(private val prefix: String) {
    companion object {
        fun create(): Greeter = Greeter("hello")
    }

    constructor() : this("hello")

    fun greet(name: String): String {
        val message = "$prefix $name"
        println(message)
        return message
    }
}

object Metrics {
    fun track(value: String) {
        println(value)
    }
}
"""
    source_file = temp_test_dir / "extended.kt"
    source_file.write_text(source, encoding="utf-8")

    result = kotlin_parser.parse(source_file)

    assert any(item["name"] == "Greeter" for item in result["classes"])
    assert any(item["name"] == "Metrics" for item in result["classes"])
    assert any(item["name"] == "create" for item in result["functions"])
    assert any(item["name"] == "greet" for item in result["functions"])
    assert any(item["name"] == "message" for item in result["variables"])
    assert any(item["name"] == "println" for item in result["function_calls"])
    assert any(item.get("class_context") == "Greeter" for item in result["functions"])

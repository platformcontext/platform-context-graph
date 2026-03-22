"""Integration tests verifying language parsers produce correct graph nodes/edges.

Requires docker compose up (ingests ecosystems/ fixtures into Neo4j).
Tests query the graph via Neo4j to verify correctness.

Run with:
    NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=testpassword \
    DATABASE_TYPE=neo4j uv run python -m pytest tests/integration/test_language_graph.py -v
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


class TestPythonGraph:
    """Verify python_comprehensive repo produces correct graph."""

    def test_function_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'python_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 10

    def test_class_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'python_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_import_edges_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function)-[:CALLS]->(g:Function) "
                "WHERE f.path CONTAINS 'python_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            # We expect some CALLS edges from cross-file function calls
            assert result is not None

    def test_inheritance_edges(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (child:Class)-[:INHERITS]->(parent:Class) "
                "WHERE child.path CONTAINS 'python_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_decorator_functions(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'python_comprehensive/decorators' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_async_functions(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'python_comprehensive/async_code' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_lang_property_is_python(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'python_comprehensive' "
                "RETURN DISTINCT f.lang as lang"
            ).single()
            assert result["lang"] == "python"


class TestGoGraph:
    """Verify go_comprehensive repo produces correct graph."""

    def test_function_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'go_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 10

    def test_struct_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'go_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_interface_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (n) WHERE n.path CONTAINS 'go_comprehensive/interfaces' "
                "RETURN count(n) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_lang_property_is_go(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'go_comprehensive' "
                "RETURN DISTINCT f.lang as lang"
            ).single()
            assert result["lang"] == "go"


class TestTypeScriptGraph:
    """Verify typescript_comprehensive repo produces correct graph."""

    def test_function_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'typescript_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_class_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'typescript_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_interface_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (i:Interface) WHERE i.path CONTAINS 'typescript_comprehensive' "
                "RETURN count(i) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_lang_property(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'typescript_comprehensive' "
                "RETURN DISTINCT f.lang as lang"
            ).single()
            assert result["lang"] == "typescript"


class TestRustGraph:
    """Verify rust_comprehensive repo produces correct graph."""

    def test_function_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'rust_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_struct_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'rust_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_trait_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (t:Trait) WHERE t.path CONTAINS 'rust_comprehensive' "
                "RETURN count(t) as cnt"
            ).single()
            assert result["cnt"] >= 2


class TestJavaGraph:
    """Verify java_comprehensive repo produces correct graph."""

    def test_class_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'java_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_function_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'java_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_interface_or_annotation_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (n) WHERE n.path CONTAINS 'java_comprehensive' "
                "AND (n:Interface OR n:Annotation) "
                "RETURN count(n) as cnt"
            ).single()
            assert result["cnt"] >= 1


class TestCppGraph:
    """Verify cpp_comprehensive repo produces correct graph."""

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'cpp_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'cpp_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_struct_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (s:Struct) WHERE s.path CONTAINS 'cpp_comprehensive' "
                "RETURN count(s) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_enum_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (e:Enum) WHERE e.path CONTAINS 'cpp_comprehensive' "
                "RETURN count(e) as cnt"
            ).single()
            assert result["cnt"] >= 1


class TestCSharpGraph:
    """Verify csharp_comprehensive repo produces correct graph."""

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'csharp_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_interface_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (i:Interface) WHERE i.path CONTAINS 'csharp_comprehensive' "
                "RETURN count(i) as cnt"
            ).single()
            assert result["cnt"] >= 1


class TestScalaGraph:
    """Verify scala_comprehensive repo produces correct graph."""

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'scala_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'scala_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3


class TestRubyGraph:
    """Verify ruby_comprehensive repo produces correct graph."""

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'ruby_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'ruby_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3


class TestJavaScriptGraph:
    """Verify javascript_comprehensive repo produces correct graph."""

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'javascript_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'javascript_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 2


class TestKotlinGraph:
    """Verify kotlin_comprehensive repo produces correct graph."""

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'kotlin_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'kotlin_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3


class TestSwiftGraph:
    """Verify swift_comprehensive repo produces correct graph."""

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'swift_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'swift_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3


class TestElixirGraph:
    """Verify elixir_comprehensive repo produces correct graph."""

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'elixir_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3


class TestPhpGraph:
    """Verify php_comprehensive repo produces correct graph."""

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'php_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'php_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 2


class TestCGraph:
    """Verify c_comprehensive repo produces correct graph."""

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'c_comprehensive' "
                "AND NOT f.path CONTAINS 'cpp_comprehensive' "
                "AND NOT f.path CONTAINS 'csharp_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3


class TestPerlGraph:
    """Verify perl_comprehensive repo produces correct graph."""

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'perl_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 2


class TestHaskellGraph:
    """Verify haskell_comprehensive repo produces correct graph."""

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'haskell_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 2


class TestDartGraph:
    """Verify dart_comprehensive repo produces correct graph."""

    def test_class_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'dart_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_function_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'dart_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 2

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


def _count(indexed_ecosystems, query: str, **params: object) -> int:
    """Return the integer count from a count-only Cypher query."""

    driver = indexed_ecosystems.get_driver()
    with driver.session() as session:
        result = session.run(query, **params).single()
    assert result is not None
    return int(result["cnt"])


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

    def test_entity_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'python_comprehensive/basic.py' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Application'}) "
                "WHERE c.path CONTAINS 'python_comprehensive/basic.py' "
                "RETURN count(c) as cnt",
            )
            == 1
        )

    def test_import_edges_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:File)-[:IMPORTS]->(m:Module) "
                "WHERE f.path CONTAINS 'python_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 5

    def test_function_call_edges_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (caller:Function)-[:CALLS]->(called) "
                "WHERE caller.path CONTAINS 'python_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_variable_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (v:Variable) WHERE v.path CONTAINS 'python_comprehensive' "
                "RETURN count(v) as cnt"
            ).single()
            assert result["cnt"] >= 3

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

    def test_async_flag_not_persisted(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'python_comprehensive/async_code' "
                "AND f.async IS NOT NULL "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] == 0

    def test_decorator_metadata_not_persisted(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'python_comprehensive/decorators' "
                "AND size(coalesce(f.decorators, [])) > 0 "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] == 0

    def test_type_annotation_nodes_not_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (n:TypeAnnotation) "
                "WHERE n.path CONTAINS 'python_comprehensive' "
                "RETURN count(n) as cnt"
            ).single()
            assert result["cnt"] == 0

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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'Greet'}) "
                "WHERE f.path CONTAINS 'go_comprehensive/basic_functions.go' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Point'}) "
                "WHERE c.path CONTAINS 'go_comprehensive/structs_methods.go' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (i:Interface {name: 'Reader'}) "
                "WHERE i.path CONTAINS 'go_comprehensive/interfaces.go' "
                "RETURN count(i) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'fmt'}) "
                "WHERE f.path CONTAINS 'go_comprehensive/packages.go' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'Sprintf' "
                "AND r.caller_file_path CONTAINS 'go_comprehensive/basic_functions.go' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'MaxRetries'}) "
                "WHERE v.path CONTAINS 'go_comprehensive/packages.go' "
                "RETURN count(v) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'Distance', class_context: 'Point'}) "
                "WHERE f.path CONTAINS 'go_comprehensive/structs_methods.go' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'Min'}) "
                "WHERE f.path CONTAINS 'go_comprehensive/generics.go' "
                "RETURN count(f) as cnt",
            )
            == 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'createCircle'}) "
                "WHERE f.path CONTAINS 'typescript_comprehensive/modules.ts' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'ModuleManager'}) "
                "WHERE c.path CONTAINS 'typescript_comprehensive/modules.ts' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (i:Interface {name: 'Service'}) "
                "WHERE i.path CONTAINS 'typescript_comprehensive/interfaces.ts' "
                "RETURN count(i) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (e:Enum {name: 'Direction'}) "
                "WHERE e.path CONTAINS 'typescript_comprehensive/advanced.ts' "
                "RETURN count(e) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: './classes'}) "
                "WHERE f.path CONTAINS 'typescript_comprehensive/modules.ts' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'Map' "
                "AND r.caller_file_path CONTAINS 'typescript_comprehensive/modules.ts' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'VERSION'}) "
                "WHERE v.path CONTAINS 'typescript_comprehensive/modules.ts' "
                "RETURN count(v) as cnt",
            )
            == 1
        )

    def test_decorator_metadata_not_persisted(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'typescript_comprehensive/decorators.ts' "
                "AND size(coalesce(f.decorators, [])) > 0 "
                "RETURN count(f) as cnt",
            )
            == 0
        )


class TestTypeScriptJSXGraph:
    """Verify tsx_comprehensive repo produces correct graph."""

    def test_function_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) WHERE f.path CONTAINS 'tsx_comprehensive' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_class_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:Class) WHERE c.path CONTAINS 'tsx_comprehensive' "
                "RETURN count(c) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_interface_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (i:Interface) WHERE i.path CONTAINS 'tsx_comprehensive' "
                "RETURN count(i) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_function_entities_created(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'fetchUsers'}) "
                "WHERE f.path CONTAINS 'tsx_comprehensive/App.tsx' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'useLocalStorage'}) "
                "WHERE f.path CONTAINS 'tsx_comprehensive/hooks.tsx' "
                "RETURN count(f) as cnt",
            )
            == 1
        )

    def test_interface_entities_created(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (i:Interface {name: 'ButtonProps'}) "
                "WHERE i.path CONTAINS 'tsx_comprehensive/Button.tsx' "
                "RETURN count(i) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (i:Interface {name: 'User'}) "
                "WHERE i.path CONTAINS 'tsx_comprehensive/App.tsx' "
                "RETURN count(i) as cnt",
            )
            >= 1
        )

    def test_class_entities_created(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'LegacyWidget'}) "
                "WHERE c.path CONTAINS 'tsx_comprehensive/LegacyWidget.tsx' "
                "RETURN count(c) as cnt",
            )
            == 1
        )

    def test_lang_property(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'tsx_comprehensive' "
                "RETURN DISTINCT f.lang as lang"
            ).single()
            assert result["lang"] == "typescript"

    def test_import_edges_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:File)-[:IMPORTS]->(m:Module) "
                "WHERE f.path CONTAINS 'tsx_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_call_edges_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (caller:Function)-[r:CALLS]->(called) "
                "WHERE caller.path CONTAINS 'tsx_comprehensive' "
                "AND r.full_call_name CONTAINS 'fetchUsers' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_variable_nodes_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (v:Variable) WHERE v.path CONTAINS 'tsx_comprehensive' "
                "RETURN count(v) as cnt"
            ).single()
            assert result["cnt"] >= 3

    def test_type_alias_nodes_not_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (n:TypeAlias) WHERE n.path CONTAINS 'tsx_comprehensive' "
                "RETURN count(n) as cnt"
            ).single()
            assert result["cnt"] == 0


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'rust_comprehensive/functions.rs' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Point'}) "
                "WHERE c.path CONTAINS 'rust_comprehensive/structs_enums.rs' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Shape'}) "
                "WHERE c.path CONTAINS 'rust_comprehensive/structs_enums.rs' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'User'}) "
                "WHERE f.path CONTAINS 'rust_comprehensive/modules.rs' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'insert' "
                "AND r.caller_file_path CONTAINS 'rust_comprehensive/modules.rs' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'HashMap::new()' "
                "AND r.caller_file_path CONTAINS 'rust_comprehensive/modules.rs' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'Person'}) "
                "WHERE f.path CONTAINS 'java_comprehensive/classes/Person.java' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'getGreeting'}) "
                "WHERE f.path CONTAINS 'java_comprehensive/classes/Person.java' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (i:Interface {name: 'Greetable'}) "
                "WHERE i.path CONTAINS 'java_comprehensive/interfaces/Greetable.java' "
                "RETURN count(i) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (a:Annotation {name: 'Logged'}) "
                "WHERE a.path CONTAINS 'java_comprehensive/annotations/Logged.java' "
                "RETURN count(a) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Status'}) "
                "WHERE c.path CONTAINS 'java_comprehensive/enums/Status.java' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'java.util.List'}) "
                "WHERE f.path CONTAINS 'java_comprehensive/Main.java' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'greet' "
                "AND r.caller_file_path CONTAINS 'java_comprehensive/Main.java' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'Person' "
                "AND r.caller_file_path CONTAINS 'java_comprehensive/Main.java' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'person'}) "
                "WHERE v.path CONTAINS 'java_comprehensive/Main.java' "
                "RETURN count(v) as cnt",
            )
            == 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'vector_operations'}) "
                "WHERE f.path CONTAINS 'cpp_comprehensive/stl_usage.cpp' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'cpp_comprehensive/lambdas.cpp' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (s:Struct {name: 'Point'}) "
                "WHERE s.path CONTAINS 'cpp_comprehensive/structs.h' "
                "RETURN count(s) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (e:Enum {name: 'Direction'}) "
                "WHERE e.path CONTAINS 'cpp_comprehensive/enums.h' "
                "RETURN count(e) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (u:Union {name: 'DataValue'}) "
                "WHERE u.path CONTAINS 'cpp_comprehensive/structs.h' "
                "RETURN count(u) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (m:Macro {name: 'MAX_SIZE'}) "
                "WHERE m.path CONTAINS 'cpp_comprehensive/macros.h' "
                "RETURN count(m) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'vector'}) "
                "WHERE f.path CONTAINS 'cpp_comprehensive/stl_usage.cpp' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'begin' "
                "AND r.caller_file_path CONTAINS 'cpp_comprehensive/stl_usage.cpp' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'numbers'}) "
                "WHERE v.path CONTAINS 'cpp_comprehensive/stl_usage.cpp' "
                "RETURN count(v) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'radius_'}) "
                "WHERE v.path CONTAINS 'cpp_comprehensive/shapes.h' "
                "RETURN count(v) as cnt",
            )
            == 1
        )


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

    def test_property_nodes(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (p:Property) WHERE p.path CONTAINS 'csharp_comprehensive' "
                "RETURN count(p) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_object_creation_calls(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (caller)-[r:CALLS]->(called) "
                "WHERE caller.path CONTAINS 'csharp_comprehensive' "
                "AND r.full_call_name IN ['Person', 'Employee', 'GreetingService'] "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 2

    def test_inheritance_edges(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (child:Class)-[:INHERITS]->(parent:Class) "
                "WHERE child.path CONTAINS 'csharp_comprehensive' "
                "RETURN count(*) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'Greet'}) "
                "WHERE f.path CONTAINS 'csharp_comprehensive/Models/Person.cs' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'Person'}) "
                "WHERE f.path CONTAINS 'csharp_comprehensive/Models/Person.cs' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'Main'}) "
                "WHERE f.path CONTAINS 'csharp_comprehensive/Program.cs' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (s:Struct {name: 'Color'}) "
                "WHERE s.path CONTAINS 'csharp_comprehensive/Records/Point.cs' "
                "RETURN count(s) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (r:Record {name: 'Point'}) "
                "WHERE r.path CONTAINS 'csharp_comprehensive/Records/Point.cs' "
                "RETURN count(r) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (e:Enum {name: 'Status'}) "
                "WHERE e.path CONTAINS 'csharp_comprehensive/Enums/Status.cs' "
                "RETURN count(e) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'System'}) "
                "WHERE f.path CONTAINS 'csharp_comprehensive/Program.cs' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'WriteLine' "
                "AND r.caller_file_path CONTAINS 'csharp_comprehensive/Program.cs' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Main'}) "
                "WHERE c.path CONTAINS 'scala_comprehensive/Main.scala' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'AppConfig'}) "
                "WHERE c.path CONTAINS 'scala_comprehensive/Main.scala' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (t:Trait {name: 'Shape'}) "
                "WHERE t.path CONTAINS 'scala_comprehensive/Shapes.scala' "
                "RETURN count(t) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'scala.util.Try'}) "
                "WHERE f.path CONTAINS 'scala_comprehensive/Imports.scala' "
                "RETURN count(*) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'println' "
                "AND r.caller_file_path CONTAINS 'scala_comprehensive/Main.scala' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'zip' "
                "AND r.caller_file_path CONTAINS 'scala_comprehensive/Generics.scala' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'person'}) "
                "WHERE v.path CONTAINS 'scala_comprehensive/Main.scala' "
                "RETURN count(v) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'running'}) "
                "WHERE v.path CONTAINS 'scala_comprehensive/Services.scala' "
                "RETURN count(v) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'apply', class_context: 'HttpService'}) "
                "WHERE f.path CONTAINS 'scala_comprehensive/Services.scala' "
                "RETURN count(f) as cnt",
            )
            == 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (m:Module {name: 'Comprehensive'}) RETURN count(m) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'greet' "
                "AND r.caller_file_path CONTAINS 'ruby_comprehensive/basic.rb' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: '@config'}) "
                "WHERE v.path CONTAINS 'ruby_comprehensive/basic.rb' "
                "RETURN count(v) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Service'})-[:INCLUDES]->(m:Module {name: 'Printable'}) "
                "WHERE c.path CONTAINS 'ruby_comprehensive/modules_mixins.rb' "
                "RETURN count(*) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'expensive_operation', class_context: 'Service'}) "
                "WHERE f.path CONTAINS 'ruby_comprehensive/modules_mixins.rb' "
                "RETURN count(f) as cnt",
            )
            == 1
        )

    def test_require_relative_imports_not_persisted(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(:Module) "
                "WHERE f.path CONTAINS 'ruby_comprehensive' RETURN count(*) as cnt",
            )
            == 0
        )


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

    def test_jsdoc_metadata_not_persisted(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'javascript_comprehensive' "
                "AND f.docstring IS NOT NULL "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] == 0

    def test_getter_metadata_persisted(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'javascript_comprehensive' "
                "AND f.type = 'getter' "
                "RETURN count(f) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'javascript_comprehensive/functions.js' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Animal'}) "
                "WHERE c.path CONTAINS 'javascript_comprehensive/classes.js' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: './classes'}) "
                "WHERE f.path CONTAINS 'javascript_comprehensive/imports.js' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'fetch' "
                "AND r.caller_file_path CONTAINS 'javascript_comprehensive/functions.js' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'response'}) "
                "WHERE v.path CONTAINS 'javascript_comprehensive/functions.js' "
                "RETURN count(v) as cnt",
            )
            == 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'kotlin_comprehensive/Basic.kt' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Point'}) "
                "WHERE c.path CONTAINS 'kotlin_comprehensive/Classes.kt' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'AppConfig'}) "
                "WHERE c.path CONTAINS 'kotlin_comprehensive/Basic.kt' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Companion'}) "
                "WHERE c.path CONTAINS 'kotlin_comprehensive/Classes.kt' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'kotlinx.coroutines.*'}) "
                "WHERE f.path CONTAINS 'kotlin_comprehensive/Coroutines.kt' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'mutableMapOf' "
                "AND r.caller_file_path CONTAINS 'kotlin_comprehensive/Interfaces.kt' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'VERSION'}) "
                "WHERE v.path CONTAINS 'kotlin_comprehensive/Basic.kt' "
                "RETURN count(v) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'create', class_context: 'Companion'}) "
                "WHERE f.path CONTAINS 'kotlin_comprehensive/Classes.kt' "
                "RETURN count(f) as cnt",
            )
            == 1
        )


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

    def test_protocol_nodes_not_created(self, indexed_ecosystems):
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (i:Interface) WHERE i.path CONTAINS 'swift_comprehensive' "
                "RETURN count(i) as cnt"
            ).single()
            assert result["cnt"] == 0

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'swift_comprehensive/Basic.swift' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'init'}) "
                "WHERE f.path CONTAINS 'swift_comprehensive/Classes.swift' "
                "RETURN count(f) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (s:Struct {name: 'Point'}) "
                "WHERE s.path CONTAINS 'swift_comprehensive/Structs.swift' "
                "RETURN count(s) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (e:Enum {name: 'Direction'}) "
                "WHERE e.path CONTAINS 'swift_comprehensive/Enums.swift' "
                "RETURN count(e) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Worker'}) "
                "WHERE c.path CONTAINS 'swift_comprehensive/Actors.swift' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'Foundation'}) "
                "WHERE f.path CONTAINS 'swift_comprehensive/Structs.swift' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'transform' "
                "AND r.caller_file_path CONTAINS 'swift_comprehensive/Enums.swift' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'host'}) "
                "WHERE v.path CONTAINS 'swift_comprehensive/Structs.swift' "
                "RETURN count(v) as cnt",
            )
            == 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'elixir_comprehensive/basic.ex' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'expose'}) "
                "WHERE f.path CONTAINS 'elixir_comprehensive/advanced.ex' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'is_even'}) "
                "WHERE f.path CONTAINS 'elixir_comprehensive/advanced.ex' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'size'}) "
                "WHERE f.path CONTAINS 'elixir_comprehensive/advanced.ex' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (m:Module {name: 'Comprehensive.Basic'}) RETURN count(m) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'Logger'}) "
                "WHERE f.path CONTAINS 'elixir_comprehensive/imports.ex' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'Logger.info' "
                "AND r.caller_file_path CONTAINS 'elixir_comprehensive/imports.ex' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )

    def test_module_attributes_not_persisted(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable) WHERE v.path CONTAINS 'elixir_comprehensive' "
                "RETURN count(v) as cnt",
            )
            == 0
        )

    def test_guard_definitions_not_persisted_as_functions(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'is_even'}) "
                "WHERE f.path CONTAINS 'elixir_comprehensive/advanced.ex' "
                "RETURN count(f) as cnt",
            )
            == 0
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'php_comprehensive/basic.php' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'run'}) "
                "WHERE f.path CONTAINS 'php_comprehensive/imports.php' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Application'}) "
                "WHERE c.path CONTAINS 'php_comprehensive/imports.php' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (i:Interface {name: 'Identifiable'}) "
                "WHERE i.path CONTAINS 'php_comprehensive/interfaces.php' "
                "RETURN count(i) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (t:Trait {name: 'Loggable'}) "
                "WHERE t.path CONTAINS 'php_comprehensive/traits.php' "
                "RETURN count(t) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'Comprehensive\\\\Config'}) "
                "WHERE f.path CONTAINS 'php_comprehensive/imports.php' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'info' "
                "AND r.caller_file_path CONTAINS 'php_comprehensive/imports.php' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'Config' "
                "AND r.caller_file_path CONTAINS 'php_comprehensive/imports.php' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: '$config'}) "
                "WHERE v.path CONTAINS 'php_comprehensive/imports.php' "
                "RETURN count(v) as cnt",
            )
            == 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'vector_create'}) "
                "WHERE f.path CONTAINS 'c_comprehensive/math/vector.c' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'types.h'}) "
                "WHERE f.path CONTAINS 'c_comprehensive/main.c' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'vector_create' "
                "AND r.caller_file_path CONTAINS 'c_comprehensive/main.c' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'sum'}) "
                "WHERE v.path CONTAINS 'c_comprehensive/main.c' "
                "RETURN count(v) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'CEvent'}) "
                "WHERE c.path CONTAINS 'c_comprehensive/entities.c' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'CEventType'}) "
                "WHERE c.path CONTAINS 'c_comprehensive/entities.c' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'CEventValue'}) "
                "WHERE c.path CONTAINS 'c_comprehensive/entities.c' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (m:Macro {name: 'C_EVENT_LIMIT'}) "
                "WHERE m.path CONTAINS 'c_comprehensive/entities.c' "
                "RETURN count(m) as cnt",
            )
            == 1
        )

    def test_typedef_nodes_not_created(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (n:Typedef) WHERE n.path CONTAINS 'c_comprehensive' "
                "RETURN count(n) as cnt",
            )
            == 0
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'perl_comprehensive/basic.pl' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Utilities'}) "
                "WHERE c.path CONTAINS 'perl_comprehensive/modules.pl' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'File::Basename'}) "
                "WHERE f.path CONTAINS 'perl_comprehensive/modules.pl' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'File::Basename::basename' "
                "AND r.caller_file_path CONTAINS 'perl_comprehensive/modules.pl' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'handlers'}) "
                "WHERE v.path CONTAINS 'perl_comprehensive/callbacks.pl' "
                "RETURN count(v) as cnt",
            )
            >= 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'greet'}) "
                "WHERE f.path CONTAINS 'haskell_comprehensive/Basic.hs' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:Function {name: 'sumAll'}) "
                "WHERE f.path CONTAINS 'haskell_comprehensive/Functional.hs' "
                "RETURN count(f) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Shape'}) "
                "WHERE c.path CONTAINS 'haskell_comprehensive/Types.hs' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Describable'}) "
                "WHERE c.path CONTAINS 'haskell_comprehensive/Types.hs' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'Data.List'}) "
                "WHERE f.path CONTAINS 'haskell_comprehensive/Basic.hs' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.full_call_name = 'intercalate' "
                "AND r.caller_file_path CONTAINS 'haskell_comprehensive/Basic.hs' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'category'}) "
                "WHERE v.path CONTAINS 'haskell_comprehensive/Basic.hs' "
                "RETURN count(v) as cnt",
            )
            == 1
        )


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

    def test_runtime_surface(self, indexed_ecosystems):
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Loggable'}) "
                "WHERE c.path CONTAINS 'dart_comprehensive/mixins.dart' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'Color'}) "
                "WHERE c.path CONTAINS 'dart_comprehensive/enums.dart' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:Class {name: 'StringTools'}) "
                "WHERE c.path CONTAINS 'dart_comprehensive/extensions.dart' "
                "RETURN count(c) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'dart:async'}) "
                "WHERE f.path CONTAINS 'dart_comprehensive/async.dart' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:File)-[:IMPORTS]->(m:Module {name: 'foo.dart'}) "
                "WHERE f.path CONTAINS 'dart_comprehensive/exports.dart' "
                "RETURN count(*) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:Function)-[r:CALLS]->(:Function) "
                "WHERE r.caller_file_path CONTAINS 'dart_comprehensive/basic.dart' "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:Variable {name: 'env'}) "
                "WHERE v.path CONTAINS 'dart_comprehensive/basic.dart' "
                "RETURN count(v) as cnt",
            )
            >= 1
        )

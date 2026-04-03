# Java Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/java.yaml`

## Parser Contract
- Language: `java`
- Family: `language`
- Parser: `JavaTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/java.py`
- Fixture repo: `tests/fixtures/ecosystems/java_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_java_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestJavaGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Methods | `methods` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_java_parser.py::test_parse_methods` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Constructors | `constructors` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_java_parser.py::test_parse_class` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_java_parser.py::test_parse_inner_classes` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `tests/unit/parsers/test_java_parser.py::test_parse_interface` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_java_parser.py::test_parse_enum` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Annotation types | `annotation-types` | supported | `annotations` | `name, line_number` | `node:Annotation` | `tests/unit/parsers/test_java_parser.py::test_parse_annotations` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_java_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Method invocations | `method-invocations` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_java_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Object creation | `object-creation` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_java_parser.py::test_parse_object_creation_calls` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Local variables | `local-variables` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_java_parser.py::test_parse_variables_and_fields` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Field declarations | `field-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_java_parser.py::test_parse_variables_and_fields` | `tests/integration/test_language_graph.py::TestJavaGraph::test_runtime_surface` | - |
| Annotations (applied) | `annotations-applied` | partial | `annotations` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_java_parser.py::test_parse_annotations` | `tests/integration/test_language_graph.py::TestJavaGraph::test_class_nodes_created` | Annotation declarations are indexed, but annotation usage on classes, methods, and fields is not persisted as a first-class graph surface. |

## Known Limitations
- Generic type bounds and wildcards not captured as structured data
- Anonymous inner classes not separately tracked
- Lambda expressions not individually modeled as functions

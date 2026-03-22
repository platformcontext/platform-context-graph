# Kotlin Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/kotlin.yaml`

## Parser Contract
- Language: `kotlin`
- Family: `language`
- Parser: `KotlinTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/kotlin.py`
- Fixture repo: `tests/fixtures/ecosystems/kotlin_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_kotlin_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestKotlinGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_simple_declarations` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_simple_declarations` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Objects (`object`) | `objects-object` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_extended_surface` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Companion objects | `companion-objects` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_extended_surface` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_kotlin_parser.py::test_pre_scan_kotlin_keeps_public_import_surface` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_extended_surface` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Property declarations | `property-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_extended_surface` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Class context on functions | `class-context-on-functions` | supported | `functions` | `name, line_number, class_context` | `property:Function.class_context` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_extended_surface` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_runtime_surface` | - |
| Secondary constructors | `secondary-constructors` | partial | `functions` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_kotlin_parser.py::test_parse_kotlin_extended_surface` | `tests/integration/test_language_graph.py::TestKotlinGraph::test_class_nodes` | Secondary constructor syntax is parsed as part of class structure, but constructor-specific graph nodes or relationships are not persisted yet. |

## Known Limitations
- Kotlin interfaces are not separately bucketed from classes
- Extension functions are captured as regular functions without extension receiver tracking
- Coroutine suspend functions do not carry a suspend flag in the output

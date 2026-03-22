# Dart Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/dart.yaml`

## Parser Contract
- Language: `dart`
- Family: `language`
- Parser: `DartTreeSitterParser`
- Entrypoint: `src/platform_context_graph/tools/languages/dart.py`
- Fixture repo: `tests/fixtures/ecosystems/dart_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_dart_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestDartGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_dart_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Constructors | `constructors` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_dart_parser.py::test_parse_classes` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_dart_parser.py::test_parse_classes` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Mixins | `mixins` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_dart_parser.py::test_parse_mixins` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Extensions | `extensions` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_dart_parser.py::test_parse_extensions` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_dart_parser.py::test_parse_enums` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Library imports | `library-imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_dart_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Library exports | `library-exports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_dart_parser.py::test_parse_exports` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_dart_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Local variable declarations | `local-variable-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_dart_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |
| Top-level variable declarations | `top-level-variable-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_dart_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestDartGraph::test_runtime_surface` | - |

## Known Limitations
- Named constructors (`ClassName.named(...)`) are captured under the constructor name only
- Cascade notation (`..method()`) is not tracked as a distinct call chain
- `part`/`part of` directives are not modeled as import relationships

# Haskell Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/haskell.yaml`

## Parser Contract
- Language: `haskell`
- Family: `language`
- Parser: `HaskellTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/haskell.py`
- Fixture repo: `tests/fixtures/ecosystems/haskell_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_haskell_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestHaskellGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Function declarations | `function-declarations` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_haskell_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Initializer declarations | `initializer-declarations` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_haskell_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Type classes | `type-classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_haskell_parser.py::test_parse_type_classes` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Data types (struct-like) | `data-types-struct-like` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_haskell_parser.py::test_parse_data_types` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Enumerations | `enumerations` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_haskell_parser.py::test_parse_data_types` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Protocols/typeclasses | `protocols-typeclasses` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_haskell_parser.py::test_parse_type_classes` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Import declarations | `import-declarations` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_haskell_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Function call expressions | `function-call-expressions` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_haskell_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |
| Property/binding declarations | `property-binding-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_haskell_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestHaskellGraph::test_runtime_surface` | - |

## Known Limitations
- Type class instances are not modeled as inheritance relationships
- Where-clauses and let-bindings define local names that are not separately graphed
- Point-free style definitions may result in functions with no parameter information

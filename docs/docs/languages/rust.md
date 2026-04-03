# Rust Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/rust.yaml`

## Parser Contract
- Language: `rust`
- Family: `language`
- Parser: `RustTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/rust.py`
- Fixture repo: `tests/fixtures/ecosystems/rust_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_rust_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestRustGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_rust_parser.py::test_parse_functions` | `tests/integration/test_language_graph.py::TestRustGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_rust_parser.py::test_parse_structs` | `tests/integration/test_language_graph.py::TestRustGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_rust_parser.py::test_parse_enums` | `tests/integration/test_language_graph.py::TestRustGraph::test_runtime_surface` | - |
| Traits | `traits` | supported | `traits` | `name, line_number` | `node:Trait` | `tests/unit/parsers/test_rust_parser.py::test_parse_traits` | `tests/integration/test_language_graph.py::TestRustGraph::test_trait_nodes_created` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_rust_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestRustGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_rust_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestRustGraph::test_runtime_surface` | - |
| Method calls (field expressions) | `method-calls-field-expressions` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_rust_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestRustGraph::test_runtime_surface` | - |
| Scoped calls (path::fn) | `scoped-calls-path-fn` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_rust_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestRustGraph::test_runtime_surface` | - |
| Impl blocks | `impl-blocks` | partial | `impl_context` | `name, line_number` | `property:Function.context` | `tests/unit/parsers/test_rust_parser.py::test_parse_impl_block` | `tests/integration/test_language_graph.py::TestRustGraph::test_function_nodes_created` | Impl ownership is attached as function context, but impl blocks are not persisted as dedicated graph nodes or explicit implementation edges. |

## Known Limitations
- `impl Trait for Type` implementations are not tracked as distinct graph edges
- Lifetime annotations are not captured
- Macro-generated code is not traversed

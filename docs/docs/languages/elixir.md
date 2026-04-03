# Elixir Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/elixir.yaml`

## Parser Contract
- Language: `elixir`
- Family: `language`
- Parser: `ElixirTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/elixir.py`
- Fixture repo: `tests/fixtures/ecosystems/elixir_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_elixir_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestElixirGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions (`def`/`defp`) | `functions-def-defp` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_functions` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Macros (`defmacro`/`defmacrop`) | `macros-defmacro-defmacrop` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_functions` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Guards (`defguard`/`defguardp`) | `guards-defguard-defguardp` | unsupported | `functions` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_guards_and_delegates` | `tests/integration/test_language_graph.py::TestElixirGraph::test_guard_definitions_not_persisted_as_functions` | Guard definitions are not emitted into the normalized `functions` bucket and do not persist as Function nodes; today they only surface indirectly through call-like captures inside guard expressions. |
| Delegated functions (`defdelegate`) | `delegated-functions-defdelegate` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_guards_and_delegates` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Modules (`defmodule`) | `modules-defmodule` | supported | `modules` | `name, line_number` | `node:Module` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_modules` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Protocols (`defprotocol`) | `protocols-defprotocol` | partial | `modules` | `name, line_number` | `node:Module` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_modules` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | Protocol declarations are extracted and merged into generic Module nodes, but the persisted graph does not retain the `defprotocol` kind needed for end-to-end protocol-specific queries. |
| Protocol implementations (`defimpl`) | `protocol-implementations-defimpl` | partial | `modules` | `name, line_number` | `node:Module` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_modules` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | Protocol implementations are extracted, but the graph merges them into undifferentiated Module nodes and drops the `defimpl` type marker. |
| Use/import/alias/require | `use-import-alias-require` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_imports` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Dot-notation calls | `dot-notation-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_calls` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Simple function calls | `simple-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_calls` | `tests/integration/test_language_graph.py::TestElixirGraph::test_runtime_surface` | - |
| Module attributes (`@attr`) | `module-attributes-attr` | unsupported | `variables` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_elixir_parser.py::test_parse_elixir_module_attributes_not_extracted` | `tests/integration/test_language_graph.py::TestElixirGraph::test_module_attributes_not_persisted` | Module attributes are not emitted into the normalized parser payload, and the graph has no dedicated variable or metadata surface for them. |

## Known Limitations
- Multiple function clause heads for the same function are each captured as separate entries
- Pipe operator (`|>`) chains are not collapsed into a single call chain node
- GenServer callbacks are not distinguished from regular function definitions

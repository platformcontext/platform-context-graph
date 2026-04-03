# Swift Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/swift.yaml`

## Parser Contract
- Language: `swift`
- Family: `language`
- Parser: `SwiftTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/swift.py`
- Fixture repo: `tests/fixtures/ecosystems/swift_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_swift_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestSwiftGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Functions | `functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_declarations_with_current_grammar` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Initializers (`init`) | `initializers-init` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_calls_and_initializers_without_protocol_nodes` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_declarations_with_current_grammar` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `structs` | `name, line_number` | `node:Struct` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_declarations_with_current_grammar` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_declarations_with_current_grammar` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Protocols | `protocols` | unsupported | `protocols` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_calls_and_initializers_without_protocol_nodes` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_protocol_nodes_not_created` | The parser leaves the `protocols` bucket empty for the comprehensive fixture set, so protocol definitions are not available as persisted graph nodes. |
| Actors | `actors` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_declarations_with_current_grammar` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Imports | `imports` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_declarations_with_current_grammar` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Function calls | `function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_calls_and_initializers_without_protocol_nodes` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |
| Property declarations | `property-declarations` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_swift_parser.py::test_parse_swift_calls_and_initializers_without_protocol_nodes` | `tests/integration/test_language_graph.py::TestSwiftGraph::test_runtime_surface` | - |

## Known Limitations
- Property wrappers are not tracked as distinct decorators
- `@objc` and dynamic dispatch attributes are not modeled in the graph
- Computed property bodies are not traversed for embedded function calls

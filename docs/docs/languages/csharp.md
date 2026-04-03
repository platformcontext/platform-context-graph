# C# Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/csharp.yaml`

## Parser Contract
- Language: `csharp`
- Family: `language`
- Parser: `CSharpTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/csharp.py`
- Fixture repo: `tests/fixtures/ecosystems/csharp_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_csharp_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestCSharpGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Methods | `methods` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_csharp_parser.py::test_parse_methods` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Constructors | `constructors` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_csharp_parser.py::test_parse_class` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Local functions | `local-functions` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_csharp_parser.py::test_parse_local_functions` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_csharp_parser.py::test_parse_class` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Interfaces | `interfaces` | supported | `interfaces` | `name, line_number` | `node:Interface` | `tests/unit/parsers/test_csharp_parser.py::test_parse_interface` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Structs | `structs` | supported | `structs` | `name, line_number` | `node:Struct` | `tests/unit/parsers/test_csharp_parser.py::test_parse_struct` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Records | `records` | supported | `records` | `name, line_number` | `node:Record` | `tests/unit/parsers/test_csharp_parser.py::test_parse_record` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Enums | `enums` | supported | `enums` | `name, line_number` | `node:Enum` | `tests/unit/parsers/test_csharp_parser.py::test_parse_enum` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Properties | `properties` | supported | `properties` | `name, line_number` | `node:Property` | `tests/unit/parsers/test_csharp_parser.py::test_parse_properties_and_object_creation` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_property_nodes` | - |
| Using directives | `using-directives` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_csharp_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Method invocations | `method-invocations` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_csharp_parser.py::test_parse_properties_and_object_creation` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_runtime_surface` | - |
| Object creation | `object-creation` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_csharp_parser.py::test_parse_properties_and_object_creation` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_object_creation_calls` | - |
| Inheritance (`base_list`) | `inheritance-base-list` | supported | `classes` | `name, line_number, bases` | `relationship:INHERITS` | `tests/unit/parsers/test_csharp_parser.py::test_parse_inheritance` | `tests/integration/test_language_graph.py::TestCSharpGraph::test_inheritance_edges` | - |

## Known Limitations
- Extension methods are not tagged as extensions in the graph
- Partial class merging across files is not performed
- Nullable reference types (`T?`) not surfaced as distinct type metadata

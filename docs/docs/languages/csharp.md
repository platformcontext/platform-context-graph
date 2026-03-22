# C# Parser

## Parser: `CSharpTreeSitterParser` in `src/platform_context_graph/tools/languages/csharp.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Methods | `functions` | Function | Supported |
| Constructors | `functions` | Function | Supported |
| Local functions | `functions` | Function | Supported |
| Classes | `classes` | Class | Supported |
| Interfaces | `classes` (interfaces bucket) | Interface | Supported |
| Structs | `classes` (structs bucket) | Class | Supported |
| Records | `classes` (records bucket) | Class | Supported |
| Enums | `classes` (enums bucket) | Class | Supported |
| Properties | property metadata on Class | - | Supported |
| Using directives | `imports` | (IMPORTS edge) | Supported |
| Method invocations | `function_calls` | (CALLS edge) | Supported |
| Object creation | `function_calls` | (CALLS edge) | Supported |
| Inheritance (`base_list`) | `classes[].bases` | (INHERITS edge) | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/csharp_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestCSharpGraph`

## Known Limitations
- Extension methods are not tagged as extensions in the graph
- Partial class merging across files is not performed
- Nullable reference types (`T?`) not surfaced as distinct type metadata

# Perl Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/perl.yaml`

## Parser Contract
- Language: `perl`
- Family: `language`
- Parser: `PerlTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/perl.py`
- Fixture repo: `tests/fixtures/ecosystems/perl_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_perl_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestPerlGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Subroutines | `subroutines` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_perl_parser.py::test_parse_subroutines` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Packages | `packages` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_perl_parser.py::test_parse_packages` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Use statements | `use-statements` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `tests/unit/parsers/test_perl_parser.py::test_parse_imports` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Method calls | `method-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_perl_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Ambiguous function calls | `ambiguous-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_perl_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Plain function calls | `plain-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_perl_parser.py::test_parse_function_calls` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Scalar variables (`my $x`) | `scalar-variables-my-x` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_perl_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Array variables (`my @x`) | `array-variables-my-x` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_perl_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Hash variables (`my %x`) | `hash-variables-my-x` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_perl_parser.py::test_parse_variables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |

## Known Limitations
- Anonymous subroutines assigned to variables are not captured as named functions
- `AUTOLOAD` dynamic dispatch is not tracked
- `BEGIN`/`END` blocks are not modeled as distinct graph nodes

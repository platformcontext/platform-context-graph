# Perl Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `perl`
- Family: `language`
- Parser: `DefaultEngine (perl)`
- Entrypoint: `go/internal/parser/perl_haskell_language.go`
- Fixture repo: `tests/fixtures/ecosystems/perl_comprehensive/`
- Unit test suite: `go/internal/parser/engine_long_tail_test.go`
- Integration test suite: `tests/integration/test_language_graph.py::TestPerlGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Subroutines | `subroutines` | supported | `functions` | `name, line_number` | `node:Function` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlFixtures` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Packages | `packages` | supported | `classes` | `name, line_number` | `node:Class` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlCallsAndVariables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Use statements | `use-statements` | supported | `imports` | `name, line_number` | `relationship:IMPORTS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlFixtures` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Method calls | `method-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlCallsAndVariables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Ambiguous function calls | `ambiguous-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlCallsAndVariables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Plain function calls | `plain-function-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlCallsAndVariables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Scalar variables (`my $x`) | `scalar-variables-my-x` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlCallsAndVariables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Array variables (`my @x`) | `array-variables-my-x` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlCallsAndVariables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |
| Hash variables (`my %x`) | `hash-variables-my-x` | supported | `variables` | `name, line_number` | `node:Variable` | `go/internal/parser/engine_long_tail_test.go::TestDefaultEngineParsePathPerlCallsAndVariables` | `tests/integration/test_language_graph.py::TestPerlGraph::test_runtime_surface` | - |

## Known Limitations
- Anonymous subroutines assigned to variables are not captured as named functions
- `AUTOLOAD` dynamic dispatch is not tracked
- `BEGIN`/`END` blocks are not modeled as distinct graph nodes

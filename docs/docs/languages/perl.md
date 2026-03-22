# Perl Parser

## Parser: `PerlTreeSitterParser` in `src/platform_context_graph/tools/languages/perl.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Subroutines | `functions` | Function | Supported |
| Packages | `classes` | Class | Supported |
| Use statements | `imports` | (IMPORTS edge) | Supported |
| Method calls | `function_calls` | (CALLS edge) | Supported |
| Ambiguous function calls | `function_calls` | (CALLS edge) | Supported |
| Plain function calls | `function_calls` | (CALLS edge) | Supported |
| Scalar variables (`my $x`) | `variables` | Variable | Supported |
| Array variables (`my @x`) | `variables` | Variable | Supported |
| Hash variables (`my %x`) | `variables` | Variable | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/perl_comprehensive/`

## Integration Test Class
`tests/integration/test_language_graph.py::TestPerlGraph`

## Known Limitations
- Anonymous subroutines assigned to variables are not captured as named functions
- `AUTOLOAD` dynamic dispatch is not tracked
- `BEGIN`/`END` blocks are not modeled as distinct graph nodes

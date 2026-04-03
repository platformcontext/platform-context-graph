# Ruby Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/ruby.yaml`

## Parser Contract
- Language: `ruby`
- Family: `language`
- Parser: `RubyTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/ruby.py`
- Fixture repo: `tests/fixtures/ecosystems/ruby_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_ruby_parser.py`
- Integration test suite: `tests/integration/test_language_graph.py::TestRubyGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Methods (`def`) | `methods-def` | supported | `functions` | `name, line_number` | `node:Function` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_definitions` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Classes | `classes` | supported | `classes` | `name, line_number` | `node:Class` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_definitions` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Modules | `modules` | supported | `modules` | `name, line_number` | `node:Module` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_definitions` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Require/load imports | `require-load-imports` | unsupported | `imports` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_require_relative_stays_out_of_imports` | `tests/integration/test_language_graph.py::TestRubyGraph::test_require_relative_imports_not_persisted` | Ruby `require` and `require_relative` statements stay in the pre-scan import surface, but the normalized parser result does not emit persisted IMPORTS edges for the comprehensive fixture set. |
| Method calls | `method-calls` | supported | `function_calls` | `name, line_number` | `relationship:CALLS` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_runtime_surface` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Instance variable assignments | `instance-variable-assignments` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_runtime_surface` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Local variable assignments | `local-variable-assignments` | supported | `variables` | `name, line_number` | `node:Variable` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_runtime_surface` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Module inclusions (`include`/`extend`) | `module-inclusions-include-extend` | supported | `module_inclusions` | `class, module, line_number` | `relationship:INCLUDES` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_runtime_surface` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |
| Parent context (class/module) | `parent-context-class-module` | supported | `functions` | `name, line_number, class_context` | `property:Function.class_context` | `tests/unit/parsers/test_ruby_parser.py::test_parse_ruby_runtime_surface` | `tests/integration/test_language_graph.py::TestRubyGraph::test_runtime_surface` | - |

## Known Limitations
- Singleton methods (defined on specific objects) are not separated from instance methods
- `method_missing` based dynamic dispatch is not tracked
- DSL-style method definitions (e.g., ActiveRecord scopes) are captured as regular calls only

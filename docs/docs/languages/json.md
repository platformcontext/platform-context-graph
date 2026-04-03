# JSON Config Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/json.yaml`

## Parser Contract
- Language: `json`
- Family: `language`
- Parser: `JSONConfigTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/json_config.py`
- Fixture repo: `tests/fixtures/ecosystems/json_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_json_parser.py`
- Integration test suite: `tests/integration/test_json_graph.py::TestJSONGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| package.json dependencies | `package-json-dependencies` | supported | `variables` | `name, line_number, value, section` | `node:Variable` | `tests/unit/parsers/test_json_parser.py::TestJSONConfigParser::test_parse_package_json_dependencies_and_scripts` | `tests/integration/test_json_graph.py::TestJSONGraph::test_package_json_dependencies_indexed` | - |
| package.json scripts | `package-json-scripts` | supported | `functions` | `name, line_number, source` | `node:Function` | `tests/unit/parsers/test_json_parser.py::TestJSONConfigParser::test_parse_package_json_dependencies_and_scripts` | `tests/integration/test_json_graph.py::TestJSONGraph::test_package_json_scripts_indexed` | - |
| composer.json require sections | `composer-json-dependencies` | supported | `variables` | `name, line_number, value, section` | `node:Variable` | `tests/unit/parsers/test_json_parser.py::TestJSONConfigParser::test_parse_composer_json_require_sections` | `tests/integration/test_json_graph.py::TestJSONGraph::test_composer_json_dependencies_indexed` | - |
| tsconfig targeted metadata | `tsconfig-targeted-metadata` | supported | `variables` | `name, line_number, value, config_kind` | `node:Variable` | `tests/unit/parsers/test_json_parser.py::TestJSONConfigParser::test_parse_tsconfig_references_and_paths` | `tests/integration/test_json_graph.py::TestJSONGraph::test_tsconfig_json_metadata_indexed` | - |
| Generic JSON metadata only | `generic-json-metadata-only` | partial | `json_metadata` | `top_level_keys` | `property:File` | `tests/unit/parsers/test_json_parser.py::TestJSONConfigParser::test_skip_non_config_json` | `tests/integration/test_json_graph.py::TestJSONGraph::test_tsconfig_json_metadata_indexed` | Arbitrary JSON files stay intentionally quiet to avoid graph noise. |
| JSON CloudFormation templates | `cloudformation-json-delegation` | supported | `cloudformation_resources` | `name, line_number` | `node:CloudFormationResource` | `tests/unit/parsers/test_json_parser.py::TestJSONConfigParser::test_parse_cloudformation_json_template` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |

## Known Limitations
- Generic JSON files emit metadata only and do not expand arbitrary nested objects into graph nodes
- Lockfiles and minified JSON assets are intentionally kept metadata-only to avoid graph noise

# JSON Config Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/json.yaml`

## Parser Contract
- Language: `json`
- Family: `language`
- Parser: `DefaultEngine (json)`
- Entrypoint: `go/internal/parser/json_language.go`
- Fixture repo: `tests/fixtures/ecosystems/json_comprehensive/`
- Unit test suite: `go/internal/parser/json_language_test.go`
- Integration test suite: `tests/integration/test_json_graph.py::TestJSONGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| package.json dependencies | `package-json-dependencies` | supported | `variables` | `name, line_number, value, section` | `node:Variable` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathJSONPackageJSON` | `tests/integration/test_json_graph.py::TestJSONGraph::test_package_json_dependencies_indexed` | - |
| package.json scripts | `package-json-scripts` | supported | `functions` | `name, line_number, source` | `node:Function` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathJSONPackageJSON` | `tests/integration/test_json_graph.py::TestJSONGraph::test_package_json_scripts_indexed` | - |
| composer.json require sections | `composer-json-dependencies` | supported | `variables` | `name, line_number, value, section` | `node:Variable` | `go/internal/parser/json_language_test.go::TestDefaultEngineParsePathJSONPreservesDocumentOrderForMetadataAndConfigBuckets` | `tests/integration/test_json_graph.py::TestJSONGraph::test_composer_json_dependencies_indexed` | - |
| tsconfig targeted metadata | `tsconfig-targeted-metadata` | supported | `variables` | `name, line_number, value, config_kind` | `node:Variable` | `go/internal/parser/json_language_test.go::TestDefaultEngineParsePathJSONPreservesDocumentOrderForMetadataAndConfigBuckets` | `tests/integration/test_json_graph.py::TestJSONGraph::test_tsconfig_json_metadata_indexed` | - |
| Generic JSON metadata only | `generic-json-metadata-only` | partial | `json_metadata` | `top_level_keys` | `property:File` | `go/internal/parser/json_language_test.go::TestDefaultEngineParsePathJSONPreservesDocumentOrderForMetadataAndConfigBuckets` | `tests/integration/test_json_graph.py::TestJSONGraph::test_tsconfig_json_metadata_indexed` | Arbitrary JSON files stay intentionally quiet to avoid graph noise. |
| JSON CloudFormation templates | `cloudformation-json-delegation` | supported | `cloudformation_resources` | `name, line_number` | `node:CloudFormationResource` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathJSONCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |

## Known Limitations
- Generic JSON files emit metadata only and do not expand arbitrary nested objects into graph nodes
- Lockfiles and minified JSON assets are intentionally kept metadata-only to avoid graph noise

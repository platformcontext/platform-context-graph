# CloudFormation Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `cloudformation`
- Family: `iac`
- Parser: `DefaultEngine (yaml)`
- Entrypoint: `go/internal/parser/yaml_language.go`
- Fixture repo: `tests/fixtures/ecosystems/cloudformation_comprehensive/`
- Unit test suite: `go/internal/parser/engine_yaml_semantics_test.go`
- Integration test suite: `tests/integration/test_iac_graph.py::TestCloudFormationGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Resources | `resources` | supported | `cloudformation_resources` | `name, line_number, resources` | `node:CloudFormationResource` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| Parameters | `parameters` | supported | `cloudformation_parameters` | `name, line_number` | `node:CloudFormationParameter` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_parameters_indexed` | - |
| Outputs | `outputs` | supported | `cloudformation_outputs` | `name, line_number` | `node:CloudFormationOutput` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_outputs_indexed` | - |
| DependsOn | `dependson` | supported | `cloudformation_resources` | `name, line_number, depends_on` | `property:depends_on property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| Conditions | `conditions` | supported | `cloudformation_resources` | `name, line_number, condition` | `property:condition property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| Export names | `export-names` | supported | `cloudformation_outputs` | `name, line_number, export_name` | `property:export_name property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| AllowedValues | `allowedvalues` | supported | `cloudformation_parameters` | `name, line_number, allowed_values` | `property:allowed_values property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| JSON templates | `json-templates` | partial | `file_format` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathJSONCloudFormation` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | JSON-formatted templates are detected at parse time, but the comprehensive fixture and end-to-end indexing coverage are still YAML-first. |

## Known Limitations
- Intrinsic functions (!Ref, !Sub, !GetAtt) stored as string values, not resolved
- Nested stack references not linked across files
- Condition evaluation not performed

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
- Integration validation: compose-backed fixture verification (see [Local Testing Runbook](../reference/local-testing.md))

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Resources | `resources` | supported | `cloudformation_resources` | `name, line_number, resources` | `node:CloudFormationResource` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | Compose-backed fixture verification | - |
| Parameters | `parameters` | supported | `cloudformation_parameters` | `name, line_number` | `node:CloudFormationParameter` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | Compose-backed fixture verification | - |
| Outputs | `outputs` | supported | `cloudformation_outputs` | `name, line_number` | `node:CloudFormationOutput` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | Compose-backed fixture verification | - |
| DependsOn | `dependson` | supported | `cloudformation_resources` | `name, line_number, depends_on` | `property:depends_on property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | Compose-backed fixture verification | - |
| Conditions | `conditions` | supported | `cloudformation_resources` | `name, line_number, condition` | `property:condition property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | Compose-backed fixture verification | - |
| Export names | `export-names` | supported | `cloudformation_outputs` | `name, line_number, export_name` | `property:export_name property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | Compose-backed fixture verification | - |
| AllowedValues | `allowedvalues` | supported | `cloudformation_parameters` | `name, line_number, allowed_values` | `property:allowed_values property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLCloudFormation` | Compose-backed fixture verification | - |
| JSON templates | `json-templates` | supported | `cloudformation_resources` | `name, line_number, file_format` | `node:CloudFormationResource` | `go/internal/parser/cloudformation_support_test.go::TestParseCloudFormationTemplatePersistsFileFormat` | Compose-backed fixture verification | JSON-formatted templates now share the same parser path as YAML and persist `file_format` on CloudFormation rows. |

## Known Limitations
- Intrinsic functions (!Ref, !Sub, !GetAtt) stored as string values, not resolved
- Nested stack references not linked across files
- Condition evaluation not performed

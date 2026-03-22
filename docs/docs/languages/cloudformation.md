# CloudFormation Parser

## Parser: `cloudformation.py` dispatched via `InfraYAMLParser` in `src/platform_context_graph/tools/languages/yaml_infra.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Resources | `cloudformation_resources` | CloudFormationResource | Supported |
| Parameters | `cloudformation_parameters` | CloudFormationParameter | Supported |
| Outputs | `cloudformation_outputs` | CloudFormationOutput | Supported |
| DependsOn | `depends_on` property | - | Supported |
| Conditions | `condition` property | - | Supported |
| Export names | `export_name` property | - | Supported |
| AllowedValues | `allowed_values` property | - | Supported |
| JSON templates | - | - | Not wired into indexing pipeline (YAML only) |

## Detection
- Document has `AWSTemplateFormatVersion` key, OR
- Document has `Resources` where values have `Type` matching `AWS::*::*`
- Checked before K8s fallback in YAML dispatcher

## Fixture Repo
`tests/fixtures/ecosystems/cloudformation_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestCloudFormationGraph`

## Known Limitations
- Intrinsic functions (!Ref, !Sub, !GetAtt) stored as string values, not resolved
- Nested stack references not linked across files
- Condition evaluation not performed

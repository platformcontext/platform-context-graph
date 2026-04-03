# CloudFormation Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/cloudformation.yaml`

## Parser Contract
- Language: `cloudformation`
- Family: `iac`
- Parser: `InfraYAMLParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/yaml_infra.py`
- Fixture repo: `tests/fixtures/ecosystems/cloudformation_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_cloudformation_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestCloudFormationGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Resources | `resources` | supported | `cloudformation_resources` | `name, line_number, resources` | `node:CloudFormationResource` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationDetection::test_detect_by_aws_resource_type` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| Parameters | `parameters` | supported | `cloudformation_parameters` | `name, line_number` | `node:CloudFormationParameter` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationParameters::test_parse_simple_parameters` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_parameters_indexed` | - |
| Outputs | `outputs` | supported | `cloudformation_outputs` | `name, line_number` | `node:CloudFormationOutput` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationOutputs::test_parse_simple_outputs` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_outputs_indexed` | - |
| DependsOn | `dependson` | supported | `variables` | `name, line_number, depends_on` | `property:depends_on property` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationParameters::test_parse_parameter_with_allowed_values` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| Conditions | `conditions` | supported | `variables` | `name, line_number, condition` | `property:condition property` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationParameters::test_parse_parameter_with_allowed_values` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| Export names | `export-names` | supported | `imports` | `name, line_number, export_name` | `property:export_name property` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationOutputs::test_parse_output_with_export` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| AllowedValues | `allowedvalues` | supported | `variables` | `name, line_number, allowed_values` | `property:allowed_values property` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationParameters::test_parse_parameter_with_allowed_values` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | - |
| JSON templates | `json-templates` | partial | `file_format` | `name, line_number` | `none:not_persisted` | `tests/unit/parsers/test_cloudformation_parser.py::TestCloudFormationDetection::test_detect_by_template_version` | `tests/integration/test_iac_graph.py::TestCloudFormationGraph::test_cloudformation_resources_indexed` | JSON-formatted templates are detected at parse time, but the comprehensive fixture and end-to-end indexing coverage are still YAML-first. |

## Known Limitations
- Intrinsic functions (!Ref, !Sub, !GetAtt) stored as string values, not resolved
- Nested stack references not linked across files
- Condition evaluation not performed

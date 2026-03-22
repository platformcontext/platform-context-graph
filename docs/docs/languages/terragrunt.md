# Terragrunt Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/terragrunt.yaml`

## Parser Contract
- Language: `terragrunt`
- Family: `iac`
- Parser: `HCLTerraformParser`
- Entrypoint: `src/platform_context_graph/tools/languages/hcl_terraform.py`
- Fixture repo: `tests/fixtures/ecosystems/terragrunt_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_hcl_terraform_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestTerragruntGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Terragrunt config blocks (`include`, `locals`, `inputs`) | `terragrunt-config-blocks-include-locals-inputs` | supported | `terragrunt_configs` | `name, line_number` | `node:TerragruntConfig` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terragrunt_config` | `tests/integration/test_iac_graph.py::TestTerragruntGraph::test_terragrunt_configs_created` | - |
| Include block labels and paths | `include-block-labels-and-paths` | supported | `imports` | `name, line_number, labels` | `property:TerragruntConfig.path` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_resource_with_nested_blocks` | `tests/integration/test_iac_graph.py::TestTerragruntGraph::test_terragrunt_configs_created` | - |
| Locals block | `locals-block` | partial | `terragrunt_configs` | `name, line_number, locals` | `property:TerragruntConfig.locals` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_variables` | `tests/integration/test_iac_graph.py::TestTerragruntGraph::test_terragrunt_configs_created` | Locals are preserved on the Terragrunt config payload, but they are not expanded into independently queryable graph entities. |
| Inputs block | `inputs-block` | partial | `terragrunt_configs` | `name, line_number, inputs` | `property:TerragruntConfig.inputs` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_variables` | `tests/integration/test_iac_graph.py::TestTerragruntGraph::test_terragrunt_configs_created` | Inputs are stored on the Terragrunt config node, but they are not normalized into separate variable-like graph nodes today. |
| Source attribute in `terraform` block | `source-attribute-in-terraform-block` | supported | `source-attribute-in-terraform-block` | `terraform_source` | `property:TerragruntConfig.source` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_resource_with_nested_blocks` | `tests/integration/test_iac_graph.py::TestTerragruntGraph::test_terragrunt_has_terraform_source` | - |

## Known Limitations
- Dependency blocks and their `outputs` references are not modeled as graph edges
- `read_terragrunt_config()` calls are not statically resolved
- HCL function calls within `locals` are not evaluated; values are captured as raw text

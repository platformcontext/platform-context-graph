# Terraform Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/terraform.yaml`

## Parser Contract
- Language: `terraform`
- Family: `iac`
- Parser: `HCLTerraformParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/hcl_terraform.py`
- Fixture repo: `tests/fixtures/ecosystems/terraform_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_hcl_terraform_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestTerraformGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Resource blocks | `resource-blocks` | supported | `terraform_resources` | `name, line_number, resources` | `node:TerraformResource` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_resources` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_resources_created` | - |
| Variable blocks | `variable-blocks` | supported | `terraform_variables` | `name, line_number` | `node:TerraformVariable` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_variables` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_variables_created` | - |
| Output blocks | `output-blocks` | supported | `terraform_outputs` | `name, line_number` | `node:TerraformOutput` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_outputs` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_outputs_created` | - |
| Module blocks | `module-blocks` | supported | `terraform_modules` | `name, line_number` | `node:TerraformModule` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_modules` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_modules_with_source` | - |
| Data source blocks | `data-source-blocks` | supported | `terraform_data_sources` | `name, line_number` | `node:TerraformDataSource` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_data_sources` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_data_sources` | - |
| `terraform {}` block metadata | `terraform-block-metadata` | supported | `terraform-block-metadata` | `name, line_number` | `node:terraform-block-metadata` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_resource_with_nested_blocks` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_resources_created` | - |
| Provider blocks | `provider-blocks` | supported | `terraform_providers` | `name, line_number` | `node:TerraformProvider` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_providers` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_providers_created` | - |
| Locals blocks | `locals-blocks` | supported | `terraform_locals` | `name, line_number, value` | `node:TerraformLocal` | `tests/unit/parsers/test_hcl_terraform_parser.py::TestHCLTerraformParser::test_parse_terraform_locals` | `tests/integration/test_iac_graph.py::TestTerraformGraph::test_terraform_locals_created` | - |

## Known Limitations
- `count` and `for_each` meta-arguments are not expanded to model multiple resource instances
- `dynamic` blocks within resources are not traversed for nested attribute extraction
- Cross-file variable references (`var.name`, `module.name.output`) are not resolved at parse time

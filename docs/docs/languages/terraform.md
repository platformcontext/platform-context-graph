# Terraform Parser

## Parser: `HCLTerraformParser` in `src/platform_context_graph/tools/languages/hcl_terraform.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Resource blocks | `terraform_resources` | TerraformResource | Supported |
| Variable blocks | `terraform_variables` | TerraformVariable | Supported |
| Output blocks | `terraform_outputs` | TerraformOutput | Supported |
| Module blocks | `terraform_modules` | TerraformModule | Supported |
| Data source blocks | `terraform_data_sources` | TerraformDataSource | Supported |
| `terraform {}` block metadata | parsed inline | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/terraform_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestTerraformGraph`

## Known Limitations
- `count` and `for_each` meta-arguments are not expanded to model multiple resource instances
- `dynamic` blocks within resources are not traversed for nested attribute extraction
- Cross-file variable references (`var.name`, `module.name.output`) are not resolved at parse time

# Terragrunt Parser

## Parser: `HCLTerraformParser` (terragrunt mode) in `src/platform_context_graph/tools/languages/hcl_terraform.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Terragrunt config blocks (`include`, `locals`, `inputs`) | `terragrunt_configs` | TerragruntConfig | Supported |
| Include block labels and paths | label/path on TerragruntConfig | - | Supported |
| Locals block | locals on TerragruntConfig | - | Partial |
| Inputs block | inputs on TerragruntConfig | - | Partial |
| Source attribute in `terraform` block | source on TerragruntConfig | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/terragrunt_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestTerragruntGraph`

## Known Limitations
- Dependency blocks and their `outputs` references are not modeled as graph edges
- `read_terragrunt_config()` calls are not statically resolved
- HCL function calls within `locals` are not evaluated; values are captured as raw text

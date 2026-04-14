# Terraform Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `terraform`
- Family: `iac`
- Parser: `DefaultEngine (hcl)`
- Entrypoint: `go/internal/parser/hcl_language.go`
- Fixture repo: `tests/fixtures/ecosystems/terraform_comprehensive/`
- Unit test suite: `go/internal/parser/engine_infra_test.go`
- Integration validation: compose-backed fixture verification (see [Local Testing Runbook](../reference/local-testing.md))

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Resource blocks | `resource-blocks` | supported | `terraform_resources` | `name, line_number, resources` | `node:TerraformResource` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | - |
| Variable blocks | `variable-blocks` | supported | `terraform_variables` | `name, line_number` | `node:TerraformVariable` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | - |
| Output blocks | `output-blocks` | supported | `terraform_outputs` | `name, line_number` | `node:TerraformOutput` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | - |
| Module blocks | `module-blocks` | supported | `terraform_modules` | `name, line_number` | `node:TerraformModule` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | - |
| Data source blocks | `data-source-blocks` | supported | `terraform_data_sources` | `name, line_number` | `node:TerraformDataSource` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | - |
| `terraform {}` block metadata | `terraform-block-metadata` | partial | `terraform-block-metadata` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | The native HCL parser reads required provider metadata and provider blocks, but it does not materialize a standalone `terraform {}` block node. |
| Provider blocks | `provider-blocks` | supported | `terraform_providers` | `name, line_number` | `node:TerraformProvider` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | - |
| Locals blocks | `locals-blocks` | supported | `terraform_locals` | `name, line_number, value` | `node:TerraformLocal` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerraform` | Compose-backed fixture verification | - |

## Known Limitations
- `count` and `for_each` meta-arguments are not expanded to model multiple resource instances
- `dynamic` blocks within resources are not traversed for nested attribute extraction
- Cross-file variable references (`var.name`, `module.name.output`) are not resolved at parse time

# Terragrunt Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `terragrunt`
- Family: `iac`
- Parser: `DefaultEngine (hcl)`
- Entrypoint: `go/internal/parser/hcl_language.go`
- Fixture repo: `tests/fixtures/ecosystems/terragrunt_comprehensive/`
- Unit test suite: `go/internal/parser/engine_infra_test.go`
- Integration validation: compose-backed fixture verification (see [Local Testing Runbook](../reference/local-testing.md))

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Terragrunt config blocks (`include`, `locals`, `inputs`) | `terragrunt-config-blocks-include-locals-inputs` | supported | `terragrunt_configs` | `name, line_number` | `node:TerragruntConfig` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragrunt` | Compose-backed fixture verification | - |
| Include block labels | `include-block-labels` | supported | `terragrunt_configs` | `name, line_number, includes` | `property:TerragruntConfig.includes` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragrunt` | Compose-backed fixture verification | - |
| Locals block | `locals-block` | partial | `terragrunt_configs` | `name, line_number, locals` | `property:TerragruntConfig.locals` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragrunt` | Compose-backed fixture verification | Locals are preserved on the Terragrunt config payload, but they are not expanded into independently queryable graph entities. |
| Inputs block | `inputs-block` | partial | `terragrunt_configs` | `name, line_number, inputs` | `property:TerragruntConfig.inputs` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragrunt` | Compose-backed fixture verification | Inputs are stored on the Terragrunt config node, but they are not normalized into separate variable-like graph nodes today. |
| Source attribute in `terraform` block | `source-attribute-in-terraform-block` | supported | `source-attribute-in-terraform-block` | `terraform_source` | `property:TerragruntConfig.source` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragrunt` | Compose-backed fixture verification | - |

## Known Limitations
- Dependency blocks and their `outputs` references are not modeled as graph edges
- `read_terragrunt_config()` calls are not statically resolved
- HCL function calls within `locals` are not evaluated; values are captured as raw text

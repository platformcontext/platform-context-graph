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
| Dependency blocks | `dependency-blocks` | supported | `terragrunt_dependencies` | `name, line_number, config_path` | `node:TerragruntDependency` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragruntBuildsFirstClassDependencyLocalAndInputEntities` | Snapshot-backed entity proof | Dependency blocks are first-class content entities in Go, but they are not yet projected into typed provisioning graph edges. |
| Locals block | `locals-block` | supported | `terragrunt_locals` | `name, line_number, value` | `node:TerragruntLocal` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragruntBuildsFirstClassDependencyLocalAndInputEntities` | Snapshot-backed entity proof | Locals are now independently queryable through the Go content/query surface. |
| Inputs block | `inputs-block` | supported | `terragrunt_inputs` | `name, line_number, value` | `node:TerragruntInput` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragruntBuildsFirstClassDependencyLocalAndInputEntities` | Snapshot-backed entity proof | Inputs are now independently queryable through the Go content/query surface. |
| Source attribute in `terraform` block | `source-attribute-in-terraform-block` | supported | `source-attribute-in-terraform-block` | `terraform_source` | `property:TerragruntConfig.source` | `go/internal/parser/engine_infra_test.go::TestDefaultEngineParsePathHCLTerragrunt` | Compose-backed fixture verification | - |

## Known Limitations
- Dependency blocks are queryable as content entities, but their `config_path` and `outputs` references are not yet resolved into typed provisioning graph edges
- `read_terragrunt_config()` calls are not statically resolved
- HCL function calls within `locals` are not evaluated; values are captured as raw text

# ArgoCD Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `argocd`
- Family: `iac`
- Parser: `DefaultEngine (yaml)`
- Entrypoint: `go/internal/parser/yaml_language.go`
- Fixture repo: `tests/fixtures/ecosystems/argocd_comprehensive/`
- Unit test suite: `go/internal/parser/engine_yaml_semantics_test.go`
- Integration validation: compose-backed fixture verification (see [Local Testing Runbook](../reference/local-testing.md))

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| ArgoCD Applications (`Application`) | `argocd-applications-application` | supported | `argocd_applications` | `name, line_number` | `node:ArgoCDApplication` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | Compose-backed fixture verification | - |
| Application source repo URL | `application-source-repo-url` | supported | `argocd_applications` | `name, line_number, source_repo` | `property:Application.source_repo` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | Compose-backed fixture verification | - |
| Application source path | `application-source-path` | supported | `argocd_applications` | `name, line_number, source_path` | `property:Application.source_path` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | Compose-backed fixture verification | - |
| Destination namespace | `destination-namespace` | supported | `argocd_applications` | `name, line_number, namespace, dest_namespace` | `property:Application.dest_namespace` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | Compose-backed fixture verification | - |
| Destination server | `destination-server` | supported | `argocd_applications` | `name, line_number, dest_server` | `property:Application.dest_server` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | Compose-backed fixture verification | - |
| ArgoCD ApplicationSets (`ApplicationSet`) | `argocd-applicationsets-applicationset` | supported | `argocd_applicationsets` | `name, line_number` | `node:ArgoCDApplicationSet` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplicationSetNestedSources` | Compose-backed fixture verification | - |
| ApplicationSet generator source repos/paths | `applicationset-generator-source-repos-paths` | supported | `argocd_applicationsets` | `name, line_number, source_repos, source_paths, source_roots, generators` | `property:ArgoCDApplicationSet.generator_sources` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplicationSetNestedSources` | Compose-backed fixture verification | - |
| Sync policy | `sync-policy` | supported | `argocd_applications` | `name, line_number, sync_policy` | `property:Application.sync_policy` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | Compose-backed fixture verification | `syncPolicy` is normalized into a stable summary string plus normalized sync options. |

## Known Limitations
- The parser payload meets or exceeds the old Python parser, but the Go relationship/evidence layer still lacks the historical ApplicationSet discovery/deploy-source/destination-cluster chain
- Helm-specific source parameters (`helm.valueFiles`, `helm.parameters`) are not extracted as structured nodes
- ApplicationSet generator wrappers such as matrix, merge, and plugin are normalized for git source and path summaries, but plugin-specific parameters are not modeled
- `ignoreDifferences` and custom health checks are not modeled

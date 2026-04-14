# ArgoCD Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/argocd.yaml`

## Parser Contract
- Language: `argocd`
- Family: `iac`
- Parser: `DefaultEngine (yaml)`
- Entrypoint: `go/internal/parser/yaml_language.go`
- Fixture repo: `tests/fixtures/ecosystems/argocd_comprehensive/`
- Unit test suite: `go/internal/parser/engine_yaml_semantics_test.go`
- Integration test suite: `tests/integration/test_iac_graph.py::TestArgoCDGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| ArgoCD Applications (`Application`) | `argocd-applications-application` | supported | `argocd_applications` | `name, line_number` | `node:ArgoCDApplication` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Application source repo URL | `application-source-repo-url` | supported | `argocd_applications` | `name, line_number, source_repo` | `property:Application.source_repo` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Application source path | `application-source-path` | supported | `argocd_applications` | `name, line_number, source_path` | `property:Application.source_path` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Destination namespace | `destination-namespace` | supported | `argocd_applications` | `name, line_number, namespace, dest_namespace` | `property:Application.dest_namespace` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Destination server | `destination-server` | supported | `argocd_applications` | `name, line_number, dest_server` | `property:Application.dest_server` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| ArgoCD ApplicationSets (`ApplicationSet`) | `argocd-applicationsets-applicationset` | supported | `argocd_applicationsets` | `name, line_number` | `node:ArgoCDApplicationSet` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplicationSetNestedSources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applicationsets_indexed` | - |
| ApplicationSet generator source repos/paths | `applicationset-generator-source-repos-paths` | supported | `argocd_applicationsets` | `name, line_number, source_repos, source_paths, source_roots, generators` | `property:ArgoCDApplicationSet.generator_sources` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplicationSetNestedSources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applicationsets_indexed` | - |
| Sync policy | `sync-policy` | partial | `argocd_applications` | `name, line_number` | `none:not_persisted` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLArgoCDApplication` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | The native YAML parser does not currently normalize `syncPolicy` into the Argo CD payload. |

## Known Limitations
- Helm-specific source parameters (`helm.valueFiles`, `helm.parameters`) are not extracted as structured nodes
- ApplicationSet matrix generators are traversed for git sources, but merge and plugin generator variants are not normalized yet
- `ignoreDifferences` and custom health checks are not modeled

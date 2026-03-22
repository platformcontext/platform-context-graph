# ArgoCD Parser

## Parser: `InfraYAMLParser` (argocd module) in `src/platform_context_graph/tools/languages/yaml_infra.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| ArgoCD Applications (`Application`) | `argocd_applications` | ArgoCDApplication | Supported |
| Application source repo URL | source_repo on Application | - | Supported |
| Application source path | source_path on Application | - | Supported |
| Destination namespace | destination_namespace on Application | - | Supported |
| Destination server | destination_server on Application | - | Supported |
| ArgoCD ApplicationSets (`ApplicationSet`) | `argocd_applicationsets` | ArgoCDApplicationSet | Supported |
| ApplicationSet generator source repos/paths | generator metadata | - | Supported |
| Sync policy | sync_policy on Application | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/argocd_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestArgoCDGraph`

## Known Limitations
- Helm-specific source parameters (`helm.valueFiles`, `helm.parameters`) are not extracted as structured nodes
- ApplicationSet matrix and merge generators are not fully traversed
- `ignoreDifferences` and custom health checks are not modeled

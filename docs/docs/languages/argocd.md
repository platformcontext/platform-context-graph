# ArgoCD Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/argocd.yaml`

## Parser Contract
- Language: `argocd`
- Family: `iac`
- Parser: `InfraYAMLParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/yaml_infra.py`
- Fixture repo: `tests/fixtures/ecosystems/argocd_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_yaml_infra_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestArgoCDGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| ArgoCD Applications (`Application`) | `argocd-applications-application` | supported | `argocd_applications` | `name, line_number` | `node:ArgoCDApplication` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Application source repo URL | `application-source-repo-url` | supported | `argocd_applications` | `name, line_number, source_repo` | `property:Application.source_repo` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Application source path | `application-source-path` | supported | `argocd_applications` | `name, line_number, source_path` | `property:Application.source_path` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Destination namespace | `destination-namespace` | supported | `argocd_applications` | `name, line_number, namespace, destination_namespace` | `property:Application.destination_namespace` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| Destination server | `destination-server` | supported | `argocd_applications` | `name, line_number, destination_server` | `property:Application.destination_server` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |
| ArgoCD ApplicationSets (`ApplicationSet`) | `argocd-applicationsets-applicationset` | supported | `argocd_applications` | `name, line_number` | `node:ArgoCDApplicationSet` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applicationsets_indexed` | - |
| ApplicationSet generator source repos/paths | `applicationset-generator-source-repos-paths` | supported | `argocd_applicationsets` | `name, line_number, source_repo, source_repos` | `node:argocd_applicationsets` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applicationsets_indexed` | - |
| Sync policy | `sync-policy` | supported | `argocd_applications` | `name, line_number, sync_policy` | `property:Application.sync_policy` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_applicationset_matrix_generator_collects_nested_git_sources` | `tests/integration/test_iac_graph.py::TestArgoCDGraph::test_argocd_applications_indexed` | - |

## Known Limitations
- Helm-specific source parameters (`helm.valueFiles`, `helm.parameters`) are not extracted as structured nodes
- ApplicationSet matrix and merge generators are not fully traversed
- `ignoreDifferences` and custom health checks are not modeled

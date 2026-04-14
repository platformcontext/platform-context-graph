# Helm Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `helm`
- Family: `iac`
- Parser: `DefaultEngine (yaml)`
- Entrypoint: `go/internal/parser/yaml_language.go`
- Fixture repo: `tests/fixtures/ecosystems/helm_comprehensive/`
- Unit test suite: `go/internal/parser/engine_yaml_semantics_test.go`
- Integration test suite: `tests/integration/test_iac_graph.py::TestHelmGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Helm charts (`Chart.yaml`) | `helm-charts-chart-yaml` | supported | `helm_charts` | `name, line_number` | `node:HelmChart` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_chart_indexed` | - |
| Chart name, version, app version | `chart-name-version-app-version` | supported | `properties` | `name, line_number, version, app_version` | `property:HelmChart.properties` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_chart_has_properties` | - |
| Chart dependencies | `chart-dependencies` | supported | `helm_charts` | `name, line_number, dependencies` | `property:HelmChart.list` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_chart_indexed` | - |
| Values files (`values*.yaml`) | `values-files-values-yaml` | supported | `helm_values` | `name, line_number` | `node:HelmValues` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_values_indexed` | - |
| Values top-level keys | `values-top-level-keys` | supported | `helm_values` | `name, line_number, top_level_keys` | `property:HelmValues.top_level_keys` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_values_indexed` | - |

## Known Limitations
- Helm template files (`.yaml` in `templates/`) are not parsed for resource definitions
- Values references inside templates (`{{ .Values.key }}`) are not statically resolved
- Helm hooks and weights are not extracted as structured metadata

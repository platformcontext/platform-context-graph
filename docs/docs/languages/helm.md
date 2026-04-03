# Helm Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/helm.yaml`

## Parser Contract
- Language: `helm`
- Family: `iac`
- Parser: `InfraYAMLParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/yaml_infra.py`
- Fixture repo: `tests/fixtures/ecosystems/helm_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_yaml_infra_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestHelmGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Helm charts (`Chart.yaml`) | `helm-charts-chart-yaml` | supported | `helm_charts` | `name, line_number` | `node:HelmChart` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_helm_chart` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_chart_indexed` | - |
| Chart name, version, app version | `chart-name-version-app-version` | supported | `properties` | `name, line_number, version, app_version` | `property:HelmChart.properties` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_argocd_application` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_chart_has_properties` | - |
| Chart dependencies | `chart-dependencies` | supported | `helm_charts` | `name, line_number, dependencies` | `property:HelmChart.list` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_helm_chart` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_chart_indexed` | - |
| Values files (`values*.yaml`) | `values-files-values-yaml` | supported | `helm_values` | `name, line_number` | `node:HelmValues` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_helm_values` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_values_indexed` | - |
| Values top-level keys | `values-top-level-keys` | supported | `helm_values` | `name, line_number, key_count` | `property:HelmValues.key_count` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_helm_values` | `tests/integration/test_iac_graph.py::TestHelmGraph::test_helm_values_indexed` | - |

## Known Limitations
- Helm template files (`.yaml` in `templates/`) are not parsed for resource definitions
- Values references inside templates (`{{ .Values.key }}`) are not statically resolved
- Helm hooks and weights are not extracted as structured metadata

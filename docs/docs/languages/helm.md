# Helm Parser

## Parser: `InfraYAMLParser` (helm module) in `src/platform_context_graph/tools/languages/yaml_infra.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Helm charts (`Chart.yaml`) | `helm_charts` | HelmChart | Supported |
| Chart name, version, app version | properties on HelmChart | - | Supported |
| Chart dependencies | `dependencies` list on HelmChart | - | Supported |
| Values files (`values*.yaml`) | `helm_values` | HelmValues | Supported |
| Values top-level keys | key_count on HelmValues | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/helm_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestHelmGraph`

## Known Limitations
- Helm template files (`.yaml` in `templates/`) are not parsed for resource definitions
- Values references inside templates (`{{ .Values.key }}`) are not statically resolved
- Helm hooks and weights are not extracted as structured metadata

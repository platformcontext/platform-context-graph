# Kubernetes Parser

## Parser: `InfraYAMLParser` (kubernetes_manifest) in `src/platform_context_graph/tools/languages/yaml_infra.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Kubernetes resources (any `apiVersion`/`kind`) | `k8s_resources` | K8sResource | Supported |
| API version | api_version on K8sResource | - | Supported |
| Kind | kind on K8sResource | - | Supported |
| Name (`metadata.name`) | name on K8sResource | - | Supported |
| Namespace (`metadata.namespace`) | namespace on K8sResource | - | Supported |
| Labels | labels on K8sResource | - | Supported |
| Multi-document YAML support | each document parsed independently | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/kubernetes_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestKubernetesGraph`

## Known Limitations
- Container image references within Pod specs are not extracted as separate nodes
- `selector` and `matchLabels` relationships between resources are not resolved
- Custom Resource Definitions (CRDs) are parsed as generic K8s resources without schema awareness

# Kubernetes Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/tools/parser_capabilities/specs/kubernetes.yaml`

## Parser Contract
- Language: `kubernetes`
- Family: `iac`
- Parser: `InfraYAMLParser`
- Entrypoint: `src/platform_context_graph/tools/languages/yaml_infra.py`
- Fixture repo: `tests/fixtures/ecosystems/kubernetes_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_yaml_infra_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestKubernetesGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Kubernetes resources (any `apiVersion`/`kind`) | `kubernetes-resources-any-apiversion-kind` | supported | `k8s_resources` | `name, line_number, kind, version, resources` | `node:K8sResource` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_no_k8s_standalone_resources_without_api_version` | `tests/integration/test_iac_graph.py::TestKubernetesGraph::test_all_resource_kinds` | - |
| API version | `api-version` | supported | `k8s_resources` | `name, line_number, api_version, version` | `property:K8sResource.api_version` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_no_k8s_standalone_resources_without_api_version` | `tests/integration/test_iac_graph.py::TestKubernetesGraph::test_all_resource_kinds` | - |
| Kind | `kind` | supported | `k8s_resources` | `name, line_number, kind` | `property:K8sResource.kind` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_custom_domain_claim_indexed_as_k8s_resource` | `tests/integration/test_iac_graph.py::TestKubernetesGraph::test_all_resource_kinds` | - |
| Name (`metadata.name`) | `name-metadata-name` | supported | `k8s_resources` | `name, line_number` | `property:K8sResource.name` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_custom_domain_claim_indexed_as_k8s_resource` | `tests/integration/test_iac_graph.py::TestKubernetesGraph::test_all_resource_kinds` | - |
| Namespace (`metadata.namespace`) | `namespace-metadata-namespace` | supported | `k8s_resources` | `name, line_number, namespace` | `property:K8sResource.namespace` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_custom_domain_claim_indexed_as_k8s_resource` | `tests/integration/test_iac_graph.py::TestKubernetesGraph::test_all_resource_kinds` | - |
| Labels | `labels` | supported | `k8s_resources` | `name, line_number, labels` | `property:K8sResource.labels` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_custom_domain_claim_indexed_as_k8s_resource` | `tests/integration/test_iac_graph.py::TestKubernetesGraph::test_all_resource_kinds` | - |
| Multi-document YAML support | `multi-document-yaml-support` | supported | `multi-document-yaml-support` | `name, line_number` | `node:multi-document-yaml-support` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_k8s_multi_document` | `tests/integration/test_iac_graph.py::TestKubernetesGraph::test_all_resource_kinds` | - |

## Known Limitations
- Container image references within Pod specs are not extracted as separate nodes
- `selector` and `matchLabels` relationships between resources are not resolved
- Custom Resource Definitions (CRDs) are parsed as generic K8s resources without schema awareness

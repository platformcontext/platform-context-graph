# Kustomize Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/kustomize.yaml`

## Parser Contract
- Language: `kustomize`
- Family: `iac`
- Parser: `InfraYAMLParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/yaml_infra.py`
- Fixture repo: `tests/fixtures/ecosystems/kustomize_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_yaml_infra_parser.py`
- Integration test suite: `tests/integration/test_iac_graph.py::TestKustomizeGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Kustomization overlays (`kustomization.yaml`) | `kustomization-overlays-kustomization-yaml` | supported | `kustomize_overlays` | `name, line_number` | `node:KustomizeOverlay` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_kustomization` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | - |
| Namespace | `namespace` | supported | `variables` | `name, line_number, namespace` | `property:Overlay.property` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_parse_helm_values` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | - |
| Resources list | `resources-list` | supported | `k8s_resources` | `name, line_number, resources` | `property:Overlay.resources` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_no_k8s_standalone_resources_without_api_version` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_k8s_resources` | - |
| Patches list | `patches-list` | supported | `kustomize_overlays` | `name, line_number, patches` | `property:Overlay.patches` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_no_k8s_standalone_resources_without_api_version` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | - |
| Base references | `base-references` | supported | `kustomize_overlays` | `name, line_number, bases` | `property:Overlay.bases` | `tests/unit/parsers/test_yaml_infra_parser.py::TestInfraYAMLParser::test_no_k8s_standalone_resources_without_api_version` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | - |

## Known Limitations
- Strategic merge patches are not parsed for the target resource they modify
- `components` and `configurations` sections are not extracted
- Inline patch bodies within `kustomization.yaml` are not traversed for field-level details

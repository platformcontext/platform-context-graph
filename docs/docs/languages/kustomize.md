# Kustomize Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/kustomize.yaml`

## Parser Contract
- Language: `kustomize`
- Family: `iac`
- Parser: `DefaultEngine (yaml)`
- Entrypoint: `go/internal/parser/yaml_language.go`
- Fixture repo: `tests/fixtures/ecosystems/kustomize_comprehensive/`
- Unit test suite: `go/internal/parser/engine_yaml_semantics_test.go`
- Integration test suite: `tests/integration/test_iac_graph.py::TestKustomizeGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Kustomization overlays (`kustomization.yaml`) | `kustomization-overlays-kustomization-yaml` | supported | `kustomize_overlays` | `name, line_number` | `node:KustomizeOverlay` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | - |
| Namespace | `namespace` | supported | `variables` | `name, line_number, namespace` | `property:Overlay.property` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | - |
| Resources list | `resources-list` | supported | `kustomize_overlays` | `name, line_number, resources` | `property:Overlay.resources` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_k8s_resources` | - |
| Patches list | `patches-list` | supported | `kustomize_overlays` | `name, line_number, patches` | `property:Overlay.patches` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | - |
| Base references | `base-references` | partial | `kustomize_overlays` | `name, line_number, resources` | `none:not_persisted` | `go/internal/parser/engine_yaml_semantics_test.go::TestDefaultEngineParsePathYAMLKustomizeAndHelm` | `tests/integration/test_iac_graph.py::TestKustomizeGraph::test_kustomize_overlays_indexed` | Base references remain part of the normalized `resources` list instead of a separate `bases` field in the native YAML payload. |

## Known Limitations
- Strategic merge patches are not parsed for the target resource they modify
- `components` and `configurations` sections are not extracted
- Inline patch bodies within `kustomization.yaml` are not traversed for field-level details

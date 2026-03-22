# Kustomize Parser

## Parser: `InfraYAMLParser` (kustomize module) in `src/platform_context_graph/tools/languages/yaml_infra.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Kustomization overlays (`kustomization.yaml`) | `kustomize_overlays` | KustomizeOverlay | Supported |
| Namespace | namespace property on Overlay | - | Supported |
| Resources list | resources on Overlay | - | Supported |
| Patches list | patches on Overlay | - | Supported |
| Base references | bases on Overlay | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/kustomize_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestKustomizeGraph`

## Known Limitations
- Strategic merge patches are not parsed for the target resource they modify
- `components` and `configurations` sections are not extracted
- Inline patch bodies within `kustomization.yaml` are not traversed for field-level details

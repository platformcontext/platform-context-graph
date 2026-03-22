# Crossplane Parser

## Parser: `InfraYAMLParser` (crossplane module) in `src/platform_context_graph/tools/languages/yaml_infra.py`

## Extracted Features
| Feature | Dict Key | Graph Node | Status |
|---------|----------|------------|--------|
| Composite Resource Definitions (XRDs) | `crossplane_xrds` | CrossplaneXRD | Supported |
| XRD group, kind, version | properties on XRD | - | Supported |
| Compositions | `crossplane_compositions` | CrossplaneComposition | Supported |
| Composition composite type ref | composite_type_ref on Composition | - | Supported |
| Composition resources list | resources on Composition | - | Supported |
| Claims | `crossplane_claims` | CrossplaneClaim | Supported |
| Claim composite type ref | composite_type_ref on Claim | - | Supported |

## Fixture Repo
`tests/fixtures/ecosystems/crossplane_comprehensive/`

## Integration Test Class
`tests/integration/test_iac_graph.py::TestCrossplaneGraph`

## Known Limitations
- Composition patch transforms are not modeled as graph edges
- XRD validation schema details are not extracted
- Usage of Composition Functions (pipeline steps) is not captured as structured nodes

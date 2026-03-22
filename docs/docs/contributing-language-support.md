# Contributing Parser Support

PlatformContextGraph now treats parser support as a spec-driven contract, not a handwritten docs exercise.

The canonical source of truth for each language or IaC parser lives in:

- `src/platform_context_graph/tools/parser_capabilities/specs/<language>.yaml`

The generated outputs are:

- `docs/docs/languages/*.md`
- `docs/docs/languages/feature-matrix.md`

Do not hand-edit those generated docs. Update the YAML spec, then regenerate.

## Contract Model

Every parser has one machine-readable capability spec. Each spec records:

- parser and language identity
- fixture repo used for coverage
- the capability checklist
- known limitations

Each capability entry records:

- a stable `id`
- `status`: `supported`, `partial`, or `unsupported`
- the extracted bucket or key
- required extracted fields
- the graph or query surface that is actually exposed
- one unit-test reference
- one integration-test reference
- a rationale whenever the status is `partial` or `unsupported`

Status semantics are strict:

- `supported` means the capability is extracted, surfaced end to end, and covered by both unit and integration tests
- `partial` means only the explicitly documented subset is promised
- `unsupported` means the capability is intentionally not claimed, and the absence must still be documented and tested

Parse-only features must not remain `supported`.

## Required Workflow

1. Add or update unit tests first.
   Use the smallest parser-level test that proves the capability or regression.
2. Implement or adjust the parser behavior.
   Keep the parser output and the persisted/queryable graph surface aligned with the claimed capability.
3. Add or update integration coverage.
   The integration test must prove the capability exists end to end in the indexed graph or API surface.
4. Update the capability spec.
   Add, remove, or reclassify checklist entries in `src/platform_context_graph/tools/parser_capabilities/specs/<language>.yaml`.
5. Regenerate the docs.
   Run the generator so the public language docs and feature matrix match the spec.
6. Run the spec/doc consistency check and the relevant tests.

## Capability Spec Expectations

Use one YAML file per parser. Keep it explicit and boring. A good spec should let a reviewer answer:

- what the parser claims to extract
- what the graph actually exposes
- which test proves the parser behavior
- which test proves the end-to-end indexed behavior
- what is intentionally partial or unsupported

Example capability entry:

```yaml
- id: type-aliases
  name: Type aliases
  status: partial
  extracted_bucket: type_aliases
  required_fields:
    - name
    - line_number
  graph_surface:
    kind: none
    target: not_persisted
  unit_test: tests/unit/parsers/test_typescript_parser.py::test_parse_type_aliases
  integration_test: tests/integration/test_language_graph.py::TestTypeScriptGraph::test_function_nodes_created
  rationale: Type aliases are extracted into a dedicated parse bucket, but the persistence layer does not currently materialize TypeAlias graph nodes.
```

## Generated Docs

Generate or check the parser capability docs with:

```bash
cd /Users/allen/personal-repos/platform-context-graph
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py
```

```bash
cd /Users/allen/personal-repos/platform-context-graph
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py --check
```

The `--check` mode fails when:

- a spec references a missing test or fixture
- a `partial` or `unsupported` capability is missing a rationale
- a `supported` capability declares no surfaced graph/query target
- generated docs drift from the YAML specs

## Testing Rules

For every `supported` capability:

- one unit test must validate extraction and required fields
- one integration test must validate the persisted or queryable end-to-end behavior

For every `partial` capability:

- the spec must describe only the part that is truly supported
- tests must match that narrower claim
- the rationale must explain the missing or deferred parts

For every `unsupported` capability:

- keep it in the checklist instead of silently omitting it
- add negative coverage that proves the parser and graph surface do not overclaim support

## Review Standard

Before approving parser-support changes, check:

- the parser behavior changed under test-first discipline
- the capability YAML matches the actual parser output
- the graph/query surface matches the claimed `supported` capabilities
- the generated docs were regenerated, not hand-edited
- unit and integration references in the spec point to real tests
- `partial` and `unsupported` entries have concrete rationales

If the YAML, tests, and generated docs disagree, the spec is wrong, the code is wrong, or both. Fix the disagreement before merging.

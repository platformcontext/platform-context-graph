# Contributing Parser Support

Parser support in PlatformContextGraph is spec-driven. Each parser has a machine-readable capability spec that defines what it extracts, what the graph surfaces, and which tests prove it.

The canonical source of truth for each language or IaC parser:

```
src/platform_context_graph/parsers/capabilities/specs/<language>.yaml
```

The generated outputs:

```
docs/docs/languages/*.md
docs/docs/languages/feature-matrix.md
```

Do not hand-edit those generated docs. Update the YAML spec, then regenerate.

## Contract Model

Every parser has one capability spec that records:

- Parser and language identity
- Fixture repo used for test coverage
- The capability checklist
- Known limitations

Each capability entry includes:

- A stable `id`
- `status`: `supported`, `partial`, or `unsupported`
- The extracted bucket or key
- Required extracted fields
- The graph or query surface exposed
- One unit-test reference
- One integration-test reference
- A rationale (required for `partial` or `unsupported`)

### Status semantics

- **supported** — extracted, surfaced end-to-end, covered by unit and integration tests
- **partial** — only the documented subset is promised
- **unsupported** — intentionally not claimed, but documented so the absence is explicit

Parse-only features must not remain `supported`.

## Workflow

1. **Add or update unit tests first.**
   Use the smallest parser-level test that proves the capability or regression.

2. **Implement or adjust the parser.**
   Keep the parser output and the persisted/queryable graph surface aligned with the claimed capability.

3. **Add or update integration coverage.**
   The integration test must prove the capability exists end-to-end in the indexed graph or API surface.

4. **Update the capability spec.**
   Add, remove, or reclassify entries in the YAML spec.

5. **Regenerate the docs.**

6. **Run the spec/doc consistency check and the relevant tests.**

## Writing a Good Capability Spec

One YAML file per parser. Keep it explicit. A reviewer should be able to answer:

- What does the parser claim to extract?
- What does the graph actually expose?
- Which test proves the parser behavior?
- Which test proves the end-to-end indexed behavior?
- What is intentionally partial or unsupported?

Example entry:

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

## Generating and Checking Docs

Generate:

```bash
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py
```

Check for drift:

```bash
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py --check
```

The `--check` mode fails when:

- A spec references a missing test or fixture
- A `partial` or `unsupported` capability is missing a rationale
- A `supported` capability declares no surfaced graph/query target
- Generated docs drift from the YAML specs

## Testing Rules

**For `supported` capabilities:**

- One unit test validates extraction and required fields
- One integration test validates persisted or queryable end-to-end behavior

**For `partial` capabilities:**

- The spec describes only the part that is truly supported
- Tests match that narrower claim
- The rationale explains the missing or deferred parts

**For `unsupported` capabilities:**

- Keep it in the checklist instead of silently omitting it
- Add negative coverage proving the parser and graph surface do not overclaim

## Review Checklist

Before approving parser-support changes:

- [ ] Parser behavior changed under test-first discipline
- [ ] Capability YAML matches actual parser output
- [ ] Graph/query surface matches claimed `supported` capabilities
- [ ] Generated docs were regenerated, not hand-edited
- [ ] Unit and integration references point to real tests
- [ ] `partial` and `unsupported` entries have concrete rationales

If the YAML, tests, and generated docs disagree, fix the disagreement before merging.

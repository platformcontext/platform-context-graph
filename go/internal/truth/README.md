# Truth

## Purpose

Canonical truth-layer contract shared by reducer materialization and query
surfaces. Lets every canonical kind declare which source layers count as
evidence and lets handlers expose `truth.layer` and `truth.backend`
consistently.

## Ownership boundary

Owns the `Layer` enum and the `Contract` value that binds one canonical kind
to its accepted source layers. Reducer projection, correlation truth, and
query-side response metadata depend on these symbols rather than redefining
them.

## Exported surface

- `Layer` enum: `LayerSourceDeclaration`, `LayerAppliedDeclaration`,
  `LayerObservedResource`, `LayerCanonicalAsset`.
- `Layer.Validate`.
- `ParseLayer(raw string)` — trim and validate one layer string.
- `Contract` with `CanonicalKind` and `SourceLayers`, plus `Validate` and
  `Supports(layer)`.

## Dependencies

Standard library only.

## Telemetry

None.

## Gotchas / invariants

- `LayerCanonicalAsset` is reducer output, never a source. `Contract.Validate`
  rejects contracts that name it in `SourceLayers`.
- `SourceLayers` must be non-empty and free of duplicates.
- `Supports` is a linear scan; `SourceLayers` is short by design, so callers
  should not cache lookup results.
- Adding a new layer requires updating the parser, validator, and any
  downstream materialization that switches on layer values.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/http-api.md` for `truth.layer` / `truth.backend`

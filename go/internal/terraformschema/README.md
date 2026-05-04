# Terraformschema

## Purpose

Go-owned loader and classifier for Terraform provider schemas. Powers
resource-type identity inference and service/category labels used by the
Terraform relationship extractor and the graph projection.

## Ownership boundary

Owns provider schema parsing, identity-key inference, and the curated
service-to-category and resource-prefix-to-service maps. Relationship
extraction lives in `internal/relationships`; this package never touches the
graph or queue directly.

## Exported surface

- `AttributeSchema`, `ProviderSchemaInfo` (with `ResourceCount`).
- `LoadProviderSchema(schemaPath string)` — reads `.json` or `.json.gz`.
- `InferIdentityKeys(attributes)` — picks the stable identity key set.
- `ClassifyResourceCategory(resourceType)` and
  `ClassifyResourceService(resourceType)`.
- `DefaultSchemaDir()` — packaged schemas path, env-overridable via
  `PCG_TERRAFORM_SCHEMA_DIR`.

## Dependencies

Standard library only.

## Telemetry

None.

## Gotchas / invariants

- `LoadProviderSchema` returns `(nil, nil)` when the file does not exist or
  fails to decode; callers must treat nil as "schema unavailable" rather than
  error.
- Gzip detection is by file extension. Files without `.gz` are read as raw
  JSON regardless of their on-disk encoding.
- `nestedIdentityBlocks` currently only contains `metadata`, which is merged
  in so Kubernetes-style `metadata.name` lookups resolve.
- Identity key inference is ordered: explicit `identityKeyPatterns` win over
  generic `*_name` suffix fallbacks. The fallback set is sorted for stable
  test output.
- Adding a new provider requires regenerating the packaged schema; see
  `schemas/README.md` and `scripts/generate_terraform_provider_schema.sh`.

## Related docs

- `docs/docs/architecture.md`
- `go/internal/terraformschema/schemas/README.md`
- `scripts/generate_terraform_provider_schema.sh`
- `scripts/package_terraform_schemas.sh`

# Contentrefs

## Purpose

Extract generic, queryable references — hostnames and service-like names —
from indexed file content for Postgres-side lookup tables. Used by the
content reference projector so cross-repo discovery can find a hostname or
service token without indexing every plain word.

## Ownership boundary

See `doc.go` for the canonical contract. This package is pure pattern
extraction over already-indexed content; it never opens files, hits
Postgres, or talks to the graph.

## Exported surface

- `Hostnames(content string) []string` — normalized lower-case hostnames
  that look like runtime endpoints, not file names or property chains.
- `ServiceNames(content string) []string` — normalized lower-case
  hyphenated service-like names with at least three parts.

## Dependencies

Standard library only.

## Telemetry

None. The calling projector emits the metrics for the reference write path.

## Gotchas / invariants

- Both extractors are line-scoped and key-gated: a line must contain a
  hostname-shaped key (`host`, `url`, `endpoint`, ...) or a service-shaped
  keyword (`image:`, `chart`, `argocd`, ...) before the regex runs. This
  keeps noise out of the index.
- Hostname false-positive blocklists target file extensions
  (`*.jpg`, `*.json`), code-shaped TLDs (`.url`, `.endpoint`), CamelCase
  segments, and JS/TS prototype keywords.
- Service-name candidates require at least three hyphen-separated parts and
  length 5..100; `content-type`, `max-old-space-size`, and `pull-requests`
  are always rejected.
- Output is sorted and deduplicated for stable Postgres upserts.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/http-api.md`

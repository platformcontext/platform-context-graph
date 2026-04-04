# API Package

HTTP application assembly and router modules live here.

Keep request/response models, router wiring, and transport concerns in this
package. Shared business logic should stay in `core`, `query`, `facts`, or
`resolution`.

This package now owns:

- public HTTP API assembly
- admin control-plane routes for reindex and facts-first recovery
- facts-first inspection routes for work items, decisions, replay events, and backfill requests

It should not own queue semantics or projection logic; those stay in the
facts-first runtime packages and are surfaced here as transport contracts.

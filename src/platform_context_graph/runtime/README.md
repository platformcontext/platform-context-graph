# Runtime Package

Background ingestion, bootstrap indexing, and repo maintenance flows live here.

The top-level `platform_context_graph.runtime` package keeps the public runtime
surface stable, while `platform_context_graph.runtime.ingester` contains the
repository-ingester implementation split into focused modules.

Use this package for long-running or container-oriented runtime behavior, not
for public query surfaces.

## Runtime Roles

The deployed service shape is easiest to reason about as three primary roles:

- **API runtime** — serves HTTP and MCP using the shared `query/` layer
- **Repository ingester** — syncs repositories and drives the Git collector
- **Resolution Engine** — claims fact work items and projects canonical graph state

For SRE and tuning work, the important telemetry split is:

- **API**: request latency, errors, and tool invocation timing
- **Repository ingester / Git collector**: repository queue wait, parse, fact emission, commit/projection timing, per-repo graph/content write durations, and fact-store SQL timings
- **Resolution Engine**: work-item claim latency, queue backlog gauges, idle sleep, active-worker count, fact-load timing, projection stage durations, stage output counts, and stage failure/error-class metrics

Internally, the Git path now flows like this:

- `collectors/git/` for source discovery and parse execution
- `parsers/` for parser registry and language parsing
- `facts/` for durable source observations and the work queue
- `resolution/` for fact-driven repository, entity, relationship, workload, and platform projection
- `graph/` for canonical graph writes owned by resolution instead of the collector

During Phase 2 cutover, indexing can execute the same facts-first projection
path in-process so one indexing run still completes end-to-end on its own. The
standalone Resolution Engine service uses the same orchestration contract.

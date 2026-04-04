# Roadmap

This roadmap is the single public place for forward-looking project direction.

## Current phase

PCG is in **Phase 3: resolution maturity**.

Phase 3 builds on the facts-first runtime established in Phase 2:

- Git indexing writes durable facts into Postgres
- a Postgres work queue coordinates projection work
- the `resolution-engine` owns canonical graph projection
- deployed runtime shape is `api` + `ingester` + `resolution-engine`
- telemetry, logs, traces, and operator runbooks align to the real service shape

The immediate goal in Phase 3 is to make the system easier to operate and trust:

- classify fact-projection failures durably instead of relying on logs alone
- add operator-grade replay, dead-letter, audit, and backfill controls
- persist projection decisions with evidence and confidence summaries
- expose richer admin and CLI inspection surfaces for work items and decisions
- strengthen documentation and test guidance before the next architectural step

## Next phase

### Phase 4: Backend And Scale Decision

Use the new facts-first telemetry to decide what actually limits scale.

- measure graph write contention
- measure Postgres fact-store and queue pressure
- measure resolution-engine throughput and saturation
- decide whether Neo4j remains the right backend
- evaluate alternatives only with real performance evidence

Why it comes before the next collector:

- it is better to understand scaling limits before adding another major source
- the new telemetry should drive the backend discussion instead of assumptions

## After that

### Phase 5: Multi-Collector Expansion

After resolution maturity and backend clarity, add the next collector.

- likely start with AWS
- plug the collector into the same facts-first path
- extend canonical identity and relationship resolution across sources
- validate code -> IaC -> cloud -> documentation graph flows

Why it comes later:

- the collector model is cleaner once resolution is stronger
- backend decisions will be better informed before expanding write volume
- the next collector should build on a stable operational foundation

## Longer-term

- Deeper cloud scanning and freshness pipelines
- Stronger semantic resolution and ranking
- Richer environment comparison and blast-radius analysis
- Broader language and IaC coverage

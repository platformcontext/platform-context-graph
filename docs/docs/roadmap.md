# Roadmap

This roadmap is the single public place for forward-looking project direction.

## Current phase

PCG is finishing **Phase 2: facts-first Git projection**.

Phase 2 establishes the runtime architecture that future work builds on:

- Git indexing writes durable facts into Postgres
- a Postgres work queue coordinates projection work
- the `resolution-engine` owns canonical graph projection
- deployed runtime shape is now `api` + `ingester` + `resolution-engine`
- telemetry, logs, traces, and operator runbooks align to the real service shape

The immediate goal is Phase 2 closeout:

- complete staging and end-to-end validation
- fix any remaining defects found in real environments
- merge the app and IaC changes
- do a short stabilization pass after merge

## Next phase

### Phase 3: Resolution Maturity

This is the next priority after Phase 2 merges.

- stronger identity resolution rules
- richer provenance and confidence handling
- better replay, backfill, and admin workflows
- tighter projection parity and correctness checks
- more operational controls around failures and recovery

Why it comes next:

- the facts-first architecture is now in place
- the next highest-value work is making resolution more trustworthy and operable
- future collectors will benefit from stronger canonical resolution semantics

## After that

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

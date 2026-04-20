# PlatformContextGraph Agent Notes

Read these first before changing runtime, deployment, or observability behavior:

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/deployment/docker-compose.md`
- `docs/docs/reference/local-testing.md`
- `docs/docs/reference/telemetry/index.md`

## Runtime Contract

The deployed platform has three long-running runtimes plus one one-shot bootstrap flow:

- **API**: `pcg api start --host 0.0.0.0 --port 8080`
- **Ingester**: `/usr/local/bin/pcg-ingester`
- **Resolution Engine**: `/usr/local/bin/pcg-reducer`
- **Bootstrap Index**: `/usr/local/bin/pcg-bootstrap-index`

Build once, run many:

```bash
docker build -t platform-context-graph:dev -f Dockerfile .
```

All runtime shapes reuse the same image. Compose, Helm, and Argo CD only change
the command, env, and workload shape.

## Verification Defaults

- Docs or instruction changes: strict MkDocs build
- CLI/runtime/deployment changes: CLI integration tests plus deployment asset tests
- Facts/resolution changes: facts end-to-end and projection parity tests
- Observability changes: facts-first telemetry and logging suites
- Compose/Helm changes: deployment asset tests plus `helm lint`

Use `docs/docs/reference/local-testing.md` as the source of truth for the exact
commands.

If a change affects Docker Compose, also read
`docs/docs/deployment/docker-compose.md`. Compose host mounts must use absolute
real directories, not symlinks. On macOS, `/tmp` resolves through a symlink and
is not a safe default bind root.

## Correlation Truth Gates

Use the `pcg-correlation-truth` skill whenever a change touches workload
admission, deployable-unit correlation, materialization, deployment tracing, or
query truth in `go/internal/reducer`, `go/internal/query`, `go/internal/graph`,
`go/internal/relationships`, or correlation verification fixtures.

- Do not change correlation logic until you can explain the full path from raw
  evidence -> candidate -> admission -> projection row -> graph write -> query
  surface.
- Every correlation or materialization change MUST include one positive case,
  one negative case, and one ambiguous case. If one of those classes is missing,
  stop and add it before claiming the design is understood.
- Prove both sides of the contract: what SHOULD materialize and what MUST remain
  provenance-only. Utility repos, controller repos, deployment repos, and
  ambiguous multi-unit repos are mandatory edge-case categories.
- Namespace, folder, or repo-name heuristics MUST NOT invent environment or
  platform truth unless the value matches an explicit environment alias or is
  backed by stronger deployment evidence.
- Reducer completion timing is not valid proof. After the final logic patch, run
  a fresh rebuild/restart path and re-check the graph before concluding a miss
  is timing-related.
- Validation MUST compare fixture intent, reducer graph truth, and API/query
  truth. If any of the three disagree, do not wave it through as "close enough";
  explain the mismatch or keep digging.
- Required proof for correlation-changing work:
  focused Go tests for the touched packages, a fresh compose correlation run, a
  direct graph inspection of the canonical nodes/edges, and the affected
  query/API surfaces.
- Deployment-story or service-story changes MUST validate repo context, service
  context, and deployment trace together because one surface can look healthy
  while another still lies.

## Service Ownership

- `app/` chooses the runtime role
- `collectors/` owns Git collection
- `facts/` owns durable facts and the work queue
- `resolution/` owns projection
- `graph/` owns canonical graph writes
- `query/` owns read surfaces

Do not move runtime behavior back into one giant combined service by accident.

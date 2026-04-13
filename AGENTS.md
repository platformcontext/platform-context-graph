# PlatformContextGraph Agent Notes

Read these first before changing runtime, deployment, or observability behavior:

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/reference/local-testing.md`
- `docs/docs/reference/telemetry/index.md`

## Runtime Contract

The deployed platform has three long-running runtimes plus one one-shot bootstrap flow:

- **API**: `pcg serve start --host 0.0.0.0 --port 8080`
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

## Service Ownership

- `app/` chooses the runtime role
- `collectors/` owns Git collection
- `facts/` owns durable facts and the work queue
- `resolution/` owns projection
- `graph/` owns canonical graph writes
- `query/` owns read surfaces

Do not move runtime behavior back into one giant combined service by accident.

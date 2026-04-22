# Local Host Lifecycle

This document defines the intended shutdown and recovery sequence for the
lightweight local host.

## Normal Startup

1. acquire `owner.lock`
2. validate `VERSION`
3. validate or reclaim stale owner record
4. start embedded Postgres and wait until it accepts local connections
5. if profile is `local_authoritative`, start the local graph backend
   sidecar and wait until its Bolt socket accepts connections
6. start local host socket
7. start watcher / index pipeline
8. begin serving CLI and MCP attach traffic

Step 5 is skipped entirely on `local_lightweight`. The graph sidecar is
configured and installed independently of the PCG binary; see
`graph-backend-installation.md` and `graph-backend-operations.md`.

## Clean Shutdown

1. stop accepting new work
2. drain or cancel watcher intake
3. request child runtimes to stop and wait for them to exit cleanly
4. allow durable queues to retain any canceled in-flight projector work so the
   next local start can retry safely
5. if profile is `local_authoritative`, signal the graph backend to stop
   accepting new writes and wait for quiesce
6. flush and stop the graph backend sidecar (if present)
7. flush and stop embedded Postgres
8. remove owner record or mark shutdown complete
9. release `owner.lock`

Ordering note: Postgres outlives the child runtimes that write to it. The
current local-lightweight host requests a clean child shutdown first and then
stops Postgres only after those children have exited. If a projector batch is
canceled during shutdown, the durable Postgres queue remains the recovery point
for the next local start.

## Crash Recovery

On restart:

1. recover Postgres via normal WAL replay
2. if a graph backend PID is recorded in `owner.json`, probe its health;
   if still alive but the PCG owner is dead, attempt a clean stop through
   `pcg graph stop --force` before reclaiming
3. detect stale owner
4. reclaim ownership only after lock acquisition, liveness checks, and
   any graph-backend stop step above has succeeded
5. rebuild any derived local caches if necessary

## Concurrency Note

MCP stdio requests should be multiplexable, but the runtime must enforce bounded
concurrency rather than unbounded fan-out under heavy client load.

Initial target:

- one bounded global query worker pool per local host
- requests beyond the pool limit queue briefly or fail fast with
  `error.code=overloaded`

## Attach Model

The long-running local host owns the workspace and watcher lifecycle. Other
commands such as `pcg mcp stdio` should attach to that owner rather than trying
to become competing workspace owners.

If `pcg mcp stdio` starts and no healthy owner exists for the workspace, it may
self-host as an ephemeral owner for that workspace. In that mode it must:

- acquire normal workspace ownership
- start the same embedded Postgres and watcher lifecycle needed for its scope
- emit an operator-visible note that it is running in self-hosted local mode
- cleanly stop and release ownership when the stdio session ends

## Signal Handling

- `SIGINT`
  - graceful stop path
- `SIGTERM`
  - graceful stop path
- `SIGKILL`
  - crash-recovery path on next start

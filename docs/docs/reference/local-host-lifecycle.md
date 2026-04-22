# Local Host Lifecycle

This document defines the intended shutdown and recovery sequence for the
lightweight local host.

## Normal Startup

1. acquire `owner.lock`
2. validate `VERSION`
3. validate or reclaim stale owner record
4. start embedded Postgres and wait until it accepts local connections
5. start local host socket
6. start watcher / index pipeline
7. begin serving CLI and MCP attach traffic

## Clean Shutdown

1. stop accepting new work
2. drain or cancel watcher intake
3. drain bounded projector/index work and wait for final durable acknowledgements
4. flush and stop embedded Postgres
5. remove owner record or mark shutdown complete
6. release `owner.lock`

## Crash Recovery

On restart:

1. recover Postgres via normal WAL replay
2. detect stale owner
3. reclaim ownership only after lock acquisition and liveness checks
4. rebuild any derived local caches if necessary

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

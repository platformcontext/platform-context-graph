# pcg

## Purpose

`pcg` is the unified PCG CLI and service launcher. The same binary drives
local indexing workflows, launches the API and MCP runtimes, owns the
embedded local graph lifecycle, manages graph backend installs, runs
operator/admin workflows, and hosts the `doctor` diagnostic.

## Ownership boundary

This binary owns the Cobra command tree, flag parsing, and local owner
orchestration. It does not own service runtime internals:
`pcg api start` and `pcg mcp start` exec `pcg-api` and `pcg-mcp-server`.
`pcg graph start` owns the local-authoritative supervisor and discovers
`pcg-reducer` and `pcg-ingester` via `PATH`.

## Entry points

- `main` in `go/cmd/pcg/main.go` (delegates to `rootCmd.Execute`)
- root command in `go/cmd/pcg/root.go`
- subcommand groups:
  - service launch: `mcp`, `api`, `serve` plus aliases (`service.go`);
    `version`, `help`, `doctor` (`root.go`, `doctor.go`)
  - indexing: `index`, `list`, `stats`, `delete`, `clean`, `query`,
    `watch`, `unwatch`, `watching`, `add-package`, `finalize` plus
    `i`/`ls`/`rm`/`w` aliases (`basic.go`)
  - `graph`, `install` with `nornicdb`, `status`, `start`, `stop`,
    `logs`, `upgrade` (`graph.go`, `graph_install.go`,
    `local_graph.go`)
  - `admin`: `facts`, `reindex`, `tuning-report`, `list`, `decisions`,
    `replay`, `dead-letter`, `skip`, `backfill`, `replay-events`
  - `config`, `neo4j`, `find`, `analyze`, `ecosystem`, `workspace`,
    `local-host`

## Configuration

Persistent flags in `root.go`: `--database` sets `PCG_RUNTIME_DB_TYPE`
for the process; `-V`, `--visual` toggles interactive graph
visualization. Subcommands define their own flags. Service launch reads
the runtime env contract (`PCG_API_ADDR`, `PCG_MCP_TRANSPORT`,
`PCG_MCP_ADDR`, `PCG_POSTGRES_DSN`, `PCG_GRAPH_BACKEND`, `NEO4J_*`).

## Telemetry

The Cobra dispatcher does no OTEL bootstrap. Telemetry runs inside each
launched runtime via the shared `telemetry` package. Errors print to
`os.Stderr`; the binary exits 1 on any Cobra error.

## Gotchas / invariants

- `SilenceUsage` and `SilenceErrors` are set on the root command
- `pcg graph start` requires `pcg-reducer` and `pcg-ingester` on `PATH`;
  fresh owner runs need `go/bin` on `PATH` after rebuilding
- The default local graph path is embedded NornicDB when `pcg` is built with
  `nolocalllm`; `PCG_NORNICDB_RUNTIME=process` is the only runtime-mode
  override, while `PCG_NORNICDB_BINARY` selects process mode for a specific
  backend binary
- Embedded and process NornicDB both use the per-workspace credentials written
  under the local graph data directory; child services receive the same values
  through `PCG_NEO4J_USERNAME`, `PCG_NEO4J_PASSWORD`, `NEO4J_USERNAME`, and
  `NEO4J_PASSWORD`
- `--database` mutates the process environment via `os.Setenv`

## Related docs

- [Service runtimes](../../../docs/docs/deployment/service-runtimes.md)
- [CLI reference](../../../docs/docs/reference/cli-reference.md)
- [CLI indexing](../../../docs/docs/reference/cli-indexing.md)

// Package main runs the pcg binary, the unified Cobra-based CLI and
// MCP/API launcher for PlatformContextGraph.
//
// The binary registers root flags (`--database`, `--visual`) and a tree of
// subcommands covering local indexing (`index`, `list`, `watch`, `query`,
// `stats`), service launch (`mcp start`, `api start`, `serve`), authenticated
// local graph ownership (`graph`), backend installation (`install`),
// admin/operator workflows (`admin ...`), configuration (`config`, `neo4j`),
// discovery (`find`, `analyze`, `ecosystem`), local-host orchestration, and the
// `doctor` diagnostic. It hands off to the Go runtime binaries discovered
// through `PATH`. Exit codes reflect the underlying Cobra command result.
package main

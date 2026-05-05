// Package main runs the pcg-mcp-server binary, which serves the PCG MCP
// tool transport over stdio or HTTP backed by the same query and content
// stores as the HTTP API.
//
// When invoked with --version or -v, it prints the embedded application
// version and exits before runtime setup. Otherwise the binary boots OTEL
// telemetry, wires the query mux and the shared
// runtime admin mux, and dispatches MCP tool calls through mcp.Server. The
// transport is selected by PCG_MCP_TRANSPORT (`http` by default, also
// `stdio`); HTTP mode listens on PCG_MCP_ADDR (default :8080) and exposes
// `/sse`, `/mcp/message`, `/health`, the mounted `/api/*` routes, and the
// shared `/healthz`, `/readyz`, `/metrics`, `/admin/status` admin surface.
// SIGINT and SIGTERM trigger context cancellation and clean shutdown.
package main

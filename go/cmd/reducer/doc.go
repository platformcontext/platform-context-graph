// Package main runs the pcg-reducer binary, the long-running runtime that
// drains the reducer fact-work queue, executes domain handlers, materializes
// cross-domain truth, and writes shared edges into the configured graph
// backend.
//
// The binary boots OTEL telemetry, opens Postgres and the graph backend,
// wires the reducer service with shared-projection, code-call,
// repo-dependency, and graph-projection-phase repair runners, and hosts it
// through app.NewHostedWithStatusServer so it exposes the shared `/healthz`,
// `/readyz`, `/metrics`, and `/admin/status` admin surface. SIGINT and
// SIGTERM trigger clean shutdown through the hosted runtime drain.
package main

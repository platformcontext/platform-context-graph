// Package main runs the pcg-workflow-coordinator binary, the long-running
// runtime that normalizes triggers, claims workflow work items, and
// publishes run-state and completeness summaries.
//
// The binary boots OTEL telemetry, opens Postgres, builds coordinator.Service
// from the configured store and metrics, and hosts it through
// app.NewHostedWithStatusServer so it exposes the shared `/healthz`,
// `/readyz`, `/metrics`, and `/admin/status` admin surface. The coordinator
// ships dark by default; permanent claim ownership stays off until the
// deployment knobs documented in the runtime contract enable it. SIGINT and
// SIGTERM trigger clean shutdown through the hosted runtime drain.
package main

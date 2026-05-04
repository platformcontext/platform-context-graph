// Package main runs the projector binary, the local verification runtime
// for source-local projection: it claims projector queue items from
// Postgres, projects facts into canonical graph state, and writes content
// rows.
//
// The binary boots OTEL telemetry, opens Postgres and the canonical graph
// writer, builds projector.Service with the projector queue and reducer
// queue handles, and hosts it through app.NewHostedWithStatusServer so it
// exposes the shared `/healthz`, `/readyz`, `/metrics`, and `/admin/status`
// admin surface. SIGINT and SIGTERM trigger clean shutdown through the
// hosted runtime drain.
package main

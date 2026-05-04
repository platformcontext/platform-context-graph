// Package main runs the pcg-ingester binary, the long-running runtime that
// owns repository sync, parsing, fact emission, and source-local projection
// into the configured graph backend.
//
// The binary boots OTEL telemetry, opens Postgres and the canonical graph
// writer, registers queue observable gauges, and hosts the collector +
// projector service through app.NewHostedWithStatusServer so it exposes the
// shared `/healthz`, `/readyz`, `/metrics`, and `/admin/status` admin
// surface together with the `/admin/recovery` route. It is the only
// long-running runtime that mounts the workspace PVC in Kubernetes, runs as
// a StatefulSet, and shuts down cleanly on SIGINT or SIGTERM.
package main

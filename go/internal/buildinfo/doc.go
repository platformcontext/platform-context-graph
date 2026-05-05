// Package buildinfo exposes the application version injected at build time.
//
// Version is set via -ldflags during release builds and defaults to "dev" for
// source builds. AppVersion is the normalized accessor used by runtime, API,
// and MCP surfaces; whitespace-only overrides collapse back to "dev".
// PrintVersionFlag gives service binaries a shared early-exit path for
// --version and -v probes before they open datastores or telemetry providers.
package buildinfo

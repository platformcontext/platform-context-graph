// Package main runs the admin-status binary, which renders the shared
// PCG status report from Postgres for local CLI inspection.
//
// The binary opens the configured Postgres database via the runtime config
// helpers, loads a status report through the shared status reader, and prints
// it in either text or JSON form. It is a one-shot CLI: it does not mount the
// long-running runtime admin surface and exits as soon as the report is
// emitted (or the database connection fails).
package main

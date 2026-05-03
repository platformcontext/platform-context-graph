# Commands

Each subdirectory builds one PCG executable.

The public CLI command is `pcg`. The service binaries use PCG-prefixed names
when installed for local runtime work, such as `pcg-api`, `pcg-mcp-server`,
`pcg-ingester`, and `pcg-reducer`. Use `scripts/install-local-binaries.sh` from
the repository root when you need that exact binary set on `PATH`.

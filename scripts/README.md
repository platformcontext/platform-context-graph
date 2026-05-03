# Scripts

This directory holds local verification and helper scripts for PCG maintainers.
Most scripts assume they are run from a fresh checkout with Go, Docker,
Postgres client tools, and `rg` available.

Use `install-local-binaries.sh` when you need the full local binary set on
`PATH` with the same names PCG expects at runtime: `pcg`, `pcg-api`,
`pcg-mcp-server`, `pcg-ingester`, `pcg-reducer`, and the supporting helper
binaries.

The `verify_*_compose.sh` scripts are developer and DevOps proof lanes. They
start their own Compose project, choose ports, and tear the stack down unless
`PCG_KEEP_COMPOSE_STACK=true` is set.

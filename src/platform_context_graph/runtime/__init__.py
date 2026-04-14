"""Runtime package — write-plane services are now Go-owned.

The deployed ingester, reducer, and bootstrap-index services run as Go
binaries (``go/cmd/ingester``, ``go/cmd/reducer``, ``go/cmd/bootstrap-index``).
This package retains only read-path helpers consumed by the CLI and MCP.
"""

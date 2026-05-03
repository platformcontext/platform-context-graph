# Runtime

The runtime package owns shared process wiring: admin muxes, health and status
handlers, datastore configuration, retry policy, memory limits, API key
resolution, and Compose/runtime contract tests.

Changes here usually affect more than one binary. Update local testing docs,
Compose docs, Helm docs, or runtime admin docs when the process contract
changes.

# CLI Package

Typer entrypoint assembly and CLI support code live here.

This package is split into focused subpackages for command registration, helper
utilities, registry workflows, setup flows, visualization output, and remote
HTTP admin/query helpers.

For the current facts-first runtime, the CLI owns three important operator
surfaces:

- local service startup and runtime commands
- remote admin commands for replay, dead-letter, backfill, and decision/work-item inspection
- profile-aware remote execution against a deployed PCG HTTP service

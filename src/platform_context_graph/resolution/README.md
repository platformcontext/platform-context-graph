# Resolution Package

Canonical projection and post-index resolution logic lives here.

This package currently owns:

- `orchestration/` for the Resolution Engine claim/process loop
- `projection/` for repository, file, entity, relationship, workload, and platform projection from stored facts
- workload materialization helpers
- platform inference and platform family helpers

As PCG evolves, this package should continue absorbing shared identity,
matching, and resolution logic that does not belong to one collector or one
query surface.

For the current Git facts-first path, this package is the runtime owner of
canonical graph writes. Collectors emit facts; resolution projects graph truth.

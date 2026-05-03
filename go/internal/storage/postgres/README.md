# Postgres Storage

`storage/postgres` owns PCG relational persistence: facts, queue state, content,
status, recovery data, and workflow coordination tables.

Postgres changes must be retry-safe and observable. Think through transaction
scope, lease timing, idempotency, and partial failure before changing queue or
status writes.

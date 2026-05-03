# Collector

`collector` owns repository discovery input, snapshot collection, content shaping,
and fact emission setup for PCG indexing runs.

Keep this package focused on turning source repositories into durable facts. It
should not make graph projection decisions or query-time truth decisions; those
belong to reducer, storage, and query packages.

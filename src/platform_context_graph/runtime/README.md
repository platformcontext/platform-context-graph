# Runtime Package

Background ingestion, bootstrap indexing, and repo maintenance flows live here.

The top-level `platform_context_graph.runtime` package keeps the public runtime
surface stable, while `platform_context_graph.runtime.ingester` contains the
repository-ingester implementation split into focused modules.

Use this package for long-running or container-oriented runtime behavior, not
for public query surfaces.

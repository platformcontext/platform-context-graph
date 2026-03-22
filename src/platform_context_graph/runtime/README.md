# Runtime Package

Background sync, bootstrap indexing, and repo maintenance flows live here.

The top-level `platform_context_graph.runtime` package keeps the public runtime
surface stable, while `platform_context_graph.runtime.repo_sync` contains the
repo-sync implementation split into focused modules.

Use this package for long-running or container-oriented runtime behavior, not
for public query surfaces.

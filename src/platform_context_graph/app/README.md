# App Package

Thin service-role entrypoints live here.

Use this package to answer:

- What runtime roles does this process support?
- How does a service choose between API, Git collector, resolution-engine, and other roles?

Keep this package small. It should describe service startup shape, not own
domain logic.

Current service roles:

- `api` serves HTTP and MCP on top of the shared `query/` layer
- `git-collector` runs repo sync, discovery, parse execution, and fact emission
- `resolution-engine` claims fact work items and projects canonical graph state

The important Phase 2 boundary is that `app/` decides *which* service role
starts, while `facts/`, `collectors/`, `graph/`, and `resolution/` own the
runtime behavior behind that role.

The Git cutover still reuses the same projection code inline during indexing,
but that behavior lives in `resolution/` and `indexing/`, not in the app
entrypoint layer itself.

# App Package

Thin service-role entrypoints live here.

Use this package to answer:

- What runtime roles does this process support?
- How does a service choose between API, Git collector, resolution-engine, and other roles?

Keep this package small. It should describe service startup shape, not own
domain logic.

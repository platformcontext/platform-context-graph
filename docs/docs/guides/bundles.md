# Bundles

Bundles are portable graph snapshots. They let you load pre-indexed context without indexing everything yourself first.

They are also the explicit opt-in path for dependency internals now that normal
repository indexing excludes built-in vendored and dependency directories by
default.

## What a bundle is

A `.pcg` bundle packages graph data and metadata so it can be moved between machines or loaded into another PCG instance.

## Common commands

### Search the registry

```bash
pcg registry search react
```

### Load a bundle

```bash
pcg load react
```

### Upload a bundle to a remote service

```bash
pcg bundle upload react.pcg --service-url http://localhost:8080
```

### Export your own bundle

```bash
pcg bundle export my-project.pcg --repo /path/to/repo
```

## When bundles help

- speeding up onboarding
- shipping pre-built context for common libraries
- sharing a graph snapshot without asking everyone to index locally
- loading dependency internals deliberately instead of indexing `vendor/` or
  `node_modules/` inside every application repo

## Current caveat

Bundle workflows are centered on CLI, registry, and the HTTP import endpoint in
this repo today. MCP can load an existing bundle, but remote bundle upload is
currently an HTTP plus CLI flow rather than an MCP tool.

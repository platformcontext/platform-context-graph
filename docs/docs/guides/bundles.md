# Bundles

Bundles are portable graph snapshots. They let you load pre-indexed context without indexing everything yourself first.

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

### Export your own bundle

```bash
pcg bundle export my-project.pcg --repo /path/to/repo
```

## When bundles help

- speeding up onboarding
- shipping pre-built context for common libraries
- sharing a graph snapshot without asking everyone to index locally

## Current caveat

Bundle workflows in the public product are centered on the CLI and registry surfaces that exist in this repo today.

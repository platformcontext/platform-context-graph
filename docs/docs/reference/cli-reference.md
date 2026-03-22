# Comprehensive CLI Reference

This page lists **every single command** available in PlatformContextGraph.

## Indexing & Management

| Command | Description | Full Details |
| :--- | :--- | :--- |
| **`pcg index`** | Adds a directory to the code graph. | [details](cli-indexing.md#pcg-index) |
| **`pcg list`** | Lists all indexed repositories. | [details](cli-indexing.md#pcg-list) |
| **`pcg delete`** | Removes a repository from the graph. | [details](cli-indexing.md#pcg-delete) |
| **`pcg watch`** | Monitors a directory for real-time updates. | [details](cli-indexing.md#pcg-watch) |
| **`pcg clean`** | Removes orphaned nodes from the DB. | - |
| **`pcg stats`** | Show node count statistics. | - |

## Code Analysis

| Command | Description | Full Details |
| :--- | :--- | :--- |
| **`pcg analyze callers`** | Show what functions call X. | [details](cli-analysis.md#analyze-callers) |
| **`pcg analyze calls`** | Show what functions X calls (callees). | [details](cli-analysis.md#analyze-calls) |
| **`pcg analyze chain`** | Show path between function A and B. | [details](cli-analysis.md#analyze-chain) |
| **`pcg analyze deps`** | Show imports/dependencies for a module. | [details](cli-analysis.md#analyze-deps) |
| **`pcg analyze tree`** | Show class inheritance hierarchy. | [details](cli-analysis.md#analyze-tree) |
| **`pcg analyze complexity`** | Find complex functions (Cyclomatic). | [details](cli-analysis.md#analyze-complexity) |
| **`pcg analyze dead-code`** | Find unused functions. | [details](cli-analysis.md#analyze-dead-code) |
| **`pcg analyze overrides`** | Find method overrides in subclasses. | [details](cli-analysis.md#analyze-overrides) |
| **`pcg analyze variable`** | Find variable usage across files. | [details](cli-analysis.md#analyze-variable) |

## Discovery & Search

| Command | Description | Full Details |
| :--- | :--- | :--- |
| **`pcg find name`** | Find element by exact name. | [details](cli-analysis.md#find-name) |
| **`pcg find pattern`** | Fuzzy search (substring). | [details](cli-analysis.md#find-pattern) |
| **`pcg find type`** | List all Class/Function nodes. | [details](cli-analysis.md#find-type) |
| **`pcg find variable`** | Find variables by name. | [details](cli-analysis.md#analyze-variable) |
| **`pcg find content`** | Full-text search in source code. | [details](cli-analysis.md#find-content) |
| **`pcg find decorator`** | Find functions with `@decorator`. | [details](cli-analysis.md#find-decorator) |
| **`pcg find argument`** | Find functions with specific arg. | [details](cli-analysis.md#find-argument) |

## System & Configuration

| Command | Description | Full Details |
| :--- | :--- | :--- |
| **`pcg doctor`** | Run system health check. | [details](cli-system.md#pcg-doctor) |
| **`pcg mcp setup`** | Configure AI clients. | [details](cli-system.md#pcg-mcp-setup) |
| **`pcg neo4j setup`** | Configure Neo4j database. | [details](cli-system.md#pcg-neo4j-setup) |
| **`pcg config`** | View or modify settings. | [details](configuration.md) |
| **`pcg bundle export`** | Save graph to `.pcg` file. | [details](cli-indexing.md#pcg-bundle-commands) |
| **`pcg bundle load`** | Load graph from file/registry. | [details](cli-indexing.md#pcg-bundle-commands) |
| **`pcg registry`** | Browse cloud bundles. | [details](cli-indexing.md#pcg-registry) |

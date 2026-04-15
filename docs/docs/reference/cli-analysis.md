# CLI: Analysis & Search

Commands for extracting insights from indexed code.

## Code Analysis

### `analyze callers`

Find every function that calls a given function. Use this before refactoring to
understand who depends on it. Under the hood this routes to
`POST /api/v0/code/relationships` with `direction=incoming` and
`relationship_type=CALLS`.

```bash
pcg analyze callers process_payment
```

### `analyze calls`

The reverse — show what a function calls (its callees). Under the hood this
routes to `POST /api/v0/code/relationships` with `direction=outgoing` and
`relationship_type=CALLS`.

```bash
pcg analyze calls process_payment
```

### `analyze chain`

Find the execution path between two functions. Useful for understanding how data flows from one entry point to another.

```bash
pcg analyze chain handle_request process_payment --depth 5
```

### `analyze deps`

Show imports and dependencies for a module.

```bash
pcg analyze deps payments
```

### `analyze tree`

Show the class inheritance hierarchy for a given class.

```bash
pcg analyze tree BaseProcessor
```

### `analyze complexity`

Find functions with high cyclomatic complexity. The threshold controls the minimum complexity reported.

```bash
pcg analyze complexity --threshold 10
```

### `analyze dead-code`

Find functions with zero callers. Use `--exclude` to skip known entry points like route handlers.

```bash
pcg analyze dead-code --exclude "@route"
```

### `analyze overrides`

Show methods that override parent class methods.

```bash
pcg analyze overrides PaymentProcessor
```

### `analyze variable`

Find where a variable is defined and used across files.

```bash
pcg analyze variable MAX_RETRIES
```

---

## Discovery & Search

These commands search the graph index, not the raw filesystem. They operate on what PCG has already parsed.

### `find name`

Find code elements by exact name.

```bash
pcg find name PaymentProcessor
```

### `find pattern`

Fuzzy substring search. Use this when you don't know the exact name.

```bash
pcg find pattern payment
```

### `find type`

List all nodes of a given type: `class`, `function`, or `module`.

```bash
pcg find type class
```

### `find variable`

Find variables by name across the graph.

```bash
pcg find variable config
```

### `find content`

Full-text search across source code and docstrings.

```bash
pcg find content "shared-payments-prod"
```

### `find decorator`

Find functions with a specific decorator.

```bash
pcg find decorator @app.route
```

### `find argument`

Find functions that accept a specific argument name.

```bash
pcg find argument user_id
```

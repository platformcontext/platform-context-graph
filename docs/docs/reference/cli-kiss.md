# CLI K.I.S.S.

This page is the simple version.

If you only remember five things about `pcg`, make it these:

1. `pcg` has a local mode and a remote mode.
2. Local mode works on your machine and your local graph.
3. Remote mode is explicit and uses the HTTP API.
4. Not every command supports remote mode in v1.
5. `pcg help` shows the full public command tree.

## Quick local workflow

Index the repo you are in:

```bash
pcg index .
```

List what is indexed:

```bash
pcg list
```

Search for a symbol:

```bash
pcg find name PaymentProcessor
```

Trace callers before you change code:

```bash
pcg analyze callers process_payment
```

## Quick remote workflow

Use a deployed service directly:

```bash
pcg workspace status --service-url https://mcp-pcg.qa.ops.bgrp.io --api-key "$PCG_API_KEY"
```

Or store a profile once:

```bash
pcg config set PCG_SERVICE_URL_QA https://mcp-pcg.qa.ops.bgrp.io
pcg config set PCG_API_KEY_QA your-token-here
```

Then use the profile:

```bash
pcg workspace status --profile qa
pcg find name handle_payment --profile qa
pcg admin reindex --profile qa
```

## What works remotely today

These commands support remote mode in this branch:

- `pcg index-status`
- `pcg workspace status`
- `pcg admin reindex`
- `pcg bundle upload`
- `pcg find name`
- `pcg find pattern`
- `pcg analyze calls`
- `pcg analyze callers`
- `pcg analyze chain`
- `pcg analyze deps`
- `pcg analyze complexity`
- `pcg analyze dead-code`
- `pcg analyze overrides`
- `pcg analyze variable`

## What stays local

These are still local-only in v1:

- `pcg index`
- `pcg watch`
- `pcg visualize`
- `pcg query`
- `pcg workspace plan`
- `pcg workspace sync`
- `pcg workspace index`
- `pcg mcp *`
- `pcg api start`
- `pcg serve start`
- `pcg neo4j setup`

## Use this when you are unsure

- Start with [CLI Reference](cli-reference.md) if you need the full command map.
- Start with [Configuration](configuration.md) if you want environment keys and config details.
- Start with [HTTP API](http-api.md) if you are integrating PCG into another tool.

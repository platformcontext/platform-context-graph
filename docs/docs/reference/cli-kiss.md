# CLI K.I.S.S.

This page is the simple version.

If you only remember five things about `pcg`, make it these:

1. `pcg` has a local mode and a remote mode.
2. Local mode works on your machine and your local graph.
3. Remote mode is explicit and uses the HTTP API.
4. Not every command supports remote mode yet.
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
pcg admin facts replay --profile qa --work-item-id fact-work-123
pcg admin facts list --profile qa --status failed
```

## What works remotely today

These commands support remote mode:

- `pcg index-status`
- `pcg workspace status`
- `pcg admin reindex`
- `pcg admin tuning-report`
- `pcg admin facts replay`
- `pcg admin facts dead-letter`
- `pcg admin facts skip`
- `pcg admin facts backfill`
- `pcg admin facts list`
- `pcg admin facts decisions`
- `pcg admin facts replay-events`
- `pcg find name`
- `pcg find pattern`
- `pcg find type`
- `pcg find variable`
- `pcg find content`
- `pcg find decorator`
- `pcg find argument`
- `pcg analyze calls`
- `pcg analyze callers`
- `pcg analyze chain`
- `pcg analyze deps`
- `pcg analyze tree`
- `pcg analyze complexity`
- `pcg analyze dead-code`
- `pcg analyze overrides`
- `pcg analyze variable`

## What stays local

These are still local-only:

- `pcg index`
- `pcg watch`
- `pcg query`
- `pcg workspace plan`
- `pcg workspace sync`
- `pcg workspace index`
- `pcg mcp *`
- `pcg api start`
- `pcg serve start`
- `pcg neo4j setup`

## Commands that are intentionally removed

These names still appear in older docs, scripts, or muscle memory, but they are
not part of the supported Go CLI contract anymore:

- `pcg clean`
- `pcg delete`
- `pcg add-package`
- `pcg unwatch`
- `pcg watching`
- `pcg ecosystem index`
- `pcg ecosystem status`

Use the Go admin/status flows or the supported indexing commands instead.

## Use this when you are unsure

- Start with [CLI Reference](cli-reference.md) if you need the full command map.
- Start with [Configuration](configuration.md) if you want environment keys and config details.
- Start with [HTTP API](http-api.md) if you are integrating PCG into another tool.

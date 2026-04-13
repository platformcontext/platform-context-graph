# ADR: Resolution Owns Cross-Domain Truth

**Status:** Accepted

## Context

PCG is moving to source-specific ingestors for Git, SQL, AWS, Kubernetes, ETL,
and future domains. Each collector can observe and normalize its own source
truth, but the platform still needs one place where shared, canonical truth is
formed.

If collectors or source-local projectors perform their own cross-domain joins,
the platform will drift into several incompatible truth engines:

- Git collectors will try to infer cloud or workload truth from code alone
- cloud collectors will try to own workload identity inline
- Kubernetes collectors will try to finish deployment correlation themselves
- data and ETL collectors will create one-off lineage and ownership seams

That would recreate the procedural-beast problem in a new form.

## Decision

PCG will keep a hard ownership split:

- collectors own source observation and normalization
- source-local projectors own source-scoped materialization
- reducers own cross-domain and canonical truth

In practical terms, the **resolution layer owns cross-domain truth**.

Examples of reducer-owned domains:

- workload identity across repos, runtimes, and environments
- deployment mapping between code, IaC, and runtime assets
- cloud asset reconciliation across declared, applied, and observed layers
- ownership, governance, and quality overlays
- cross-source data lineage and consumer mapping

Collectors and source-local projectors may emit hints and evidence, but they
must not become the final authority for those shared domains.

## Why This Choice

- It keeps source-specific runtimes fast and bounded.
- It gives PCG one obvious place where canonical truth is formed.
- It prevents each new ingestor from inventing a new correlation model.
- It keeps replay, backfill, and explainability anchored to durable work-unit
  boundaries rather than ad hoc collector behavior.

## Consequences

Positive:

- Cross-domain reasoning stays consistent as new collectors land.
- Canonical truth remains explainable and replayable.
- Operators can see whether a result is source-local, reducer-owned, or still
  pending shared reconciliation.

Tradeoffs:

- The resolution layer becomes a true product subsystem, not a background
  helper.
- Some results remain eventually consistent until the relevant reducer domain
  drains.
- Collector authors need discipline to stop at evidence and hints instead of
  finishing shared inference inline.

## Implementation Guidance

- Make reducer ownership explicit for every shared domain before implementation
  fan-out begins.
- Require projector outputs to be explainable without canonical correlation.
- Require canonical query paths to reveal when source-local truth exists but
  reducer-owned truth is still pending.
- Treat any attempt to add cross-domain inference to a collector or projector
  as a design exception that must be justified in writing.

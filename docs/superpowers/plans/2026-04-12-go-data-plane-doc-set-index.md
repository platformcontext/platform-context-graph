# Go Data Plane Rewrite Documentation Index

This document is the canonical entry point for the Go data-plane rewrite
documentation set.

Use it to onboard new workers, sequence reading order, and keep architectural
decisions out of chat history and scattered review comments.

## Reading Order

Read these documents in order before implementation work begins:

1. [Go Data Plane Rewrite PRD](../specs/2026-04-12-go-data-plane-rewrite-prd.md)
2. [Go Data Plane Rewrite Statement Of Work](2026-04-12-go-data-plane-rewrite-sow.md)
3. [ADR Index](../../docs/adrs/index.md)
4. [Service Boundaries And Ownership](2026-04-12-go-data-plane-service-boundaries-and-ownership.md)
5. [Contract Freeze Plan](2026-04-12-go-data-plane-contract-freeze-plan.md)
6. [Parallel Execution Plan](2026-04-12-go-data-plane-parallel-execution-plan.md)
7. [Validation And Cutover Plan](2026-04-12-go-data-plane-validation-and-cutover-plan.md)

## Canonical Roles

| Document | Role |
| --- | --- |
| PRD | Product and architecture destination |
| SOW | Milestones, gates, and execution rules |
| ADRs | Locked design decisions and rationale |
| Service boundaries plan | Directory ownership, runtime boundaries, and allowed write scopes |
| Contract freeze plan | v1 contract shape and compatibility rules |
| Parallel execution plan | How multiple agents can work safely in parallel |
| Validation and cutover plan | How the new substrate is proven and flipped into authority |

## Documentation Rules

- New architectural decisions require an ADR update or a new ADR.
- New execution sequencing, ownership, or validation rules require a plan
  update.
- No durable design decision lives only in chat, comments, or PR review.
- The draft PR description should summarize these docs, not replace them.
- If two docs disagree, the ADR wins for design intent and the SOW wins for
  execution policy until the conflict is resolved explicitly.

## Agent Onboarding Checklist

Before starting implementation, every worker should confirm:

- which milestone and workstream they own
- which directories they are allowed to edit
- which contracts are already frozen
- which validation command proves their slice
- which document they must update if they discover a design gap

## Lock Condition

The documentation set is considered locked for implementation when:

- the PRD and SOW are accepted for the branch
- the ADR set covers the core architecture choices
- the service boundaries, contract freeze, parallel execution, and validation
  plans are present and cross-linked
- future work can be assigned without guessing where logic belongs

# Go Data Plane Rewrite Documentation Index

This document is the canonical entry point for the Go data-plane rewrite
documentation set.

Use it to onboard new workers, sequence reading order, and keep architectural
decisions out of chat history and scattered review comments.

Superseded slice plans and pre-rewrite design notes have been removed from the
active doc set. If a piece of reasoning is still needed, promote it into the
SOW, an ADR, or an operator-facing doc instead of restoring historical drift.

## Reading Order

Read these documents in order before implementation work begins:

1. [Go Data Plane Rewrite PRD](../specs/2026-04-12-go-data-plane-rewrite-prd.md)
2. [Go Data Plane Rewrite Statement Of Work](2026-04-12-go-data-plane-rewrite-sow.md)
3. [ADR Index](../../docs/adrs/index.md)
4. [Service Boundaries And Ownership](2026-04-12-go-data-plane-service-boundaries-and-ownership.md)
5. [Local Testing Runbook](../../docs/reference/local-testing.md)
6. [Cloud Validation Runbook](../../docs/reference/cloud-validation.md)
7. [Service Runtimes](../../docs/deployment/service-runtimes.md)
8. [System Architecture](../../docs/architecture.md)
9. [Relationship Mapping](../../docs/reference/relationship-mapping.md)
10. [Relationship Mapping Observability And Examples](../../docs/reference/relationship-mapping-observability.md)
11. [Collector Authoring Guide](../../docs/guides/collector-authoring.md)

## Canonical Roles

| Document | Role |
| --- | --- |
| PRD | Product and architecture destination |
| SOW | Milestones, gates, and execution rules |
| ADRs | Locked design decisions and rationale |
| Service boundaries plan | Directory ownership, runtime boundaries, and allowed write scopes |
| Local testing runbook | Default local verification matrix and Compose proof rules |
| Cloud validation runbook | Hosted verification order and operator evidence checks |
| Service runtimes | Current runtime ownership, commands, and operational boundaries |
| Collector authoring guide | How new ingestors fit the shared scope/generation/fact/reducer contract |
| Architecture and traversal references | Canonical end-to-end flow, ownership boundaries, and repair-path limits |
| Relationship-mapping observability appendix | The traversal appendix and observability examples for the relationship map |

## Documentation Rules

- New architectural decisions require an ADR update or a new ADR.
- New execution sequencing, ownership, or validation rules require a plan
  update.
- New data-plane flow changes require the end-to-end traversal map to be
  updated in the repo docs.
- New collector onboarding rules require the collector authoring guide to be
  updated alongside the architecture page.
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
- the service boundaries and current operator runbooks are present and
  cross-linked
- future work can be assigned without guessing where logic belongs

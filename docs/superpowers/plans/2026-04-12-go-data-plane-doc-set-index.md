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
6. [Milestone Operating Model](2026-04-12-go-data-plane-milestone-operating-model.md)
7. [Milestone 1: Native Git Cutover And Operability](2026-04-12-go-data-plane-milestone-01-native-git-cutover.md)
8. [Parallel Execution Plan](2026-04-12-go-data-plane-parallel-execution-plan.md)
9. [Validation And Cutover Plan](2026-04-12-go-data-plane-validation-and-cutover-plan.md)
10. [Collector Authoring Guide](../../docs/guides/collector-authoring.md)
11. [Cloud Validation Runbook](../../docs/reference/cloud-validation.md)
12. [System Architecture](../../docs/architecture.md)
13. [Relationship Mapping](../../docs/reference/relationship-mapping.md)
14. [Relationship Mapping Observability And Examples](../../docs/reference/relationship-mapping-observability.md)
15. [Go Write-Plane Conversion Cutover](2026-04-13-go-write-plane-conversion-cutover.md)
16. [Go Data Plane Ownership Completion Plan](2026-04-13-go-data-plane-ownership-completion-plan.md)
17. [Terraform Provider Schema Go-Port Checklist](2026-04-13-terraform-provider-schema-go-port-checklist.md)
18. [Terraform Provider Schema Go-Port Implementation Plan](2026-04-13-terraform-provider-schema-go-port-implementation.md)

## Canonical Roles

| Document | Role |
| --- | --- |
| PRD | Product and architecture destination |
| SOW | Milestones, gates, and execution rules |
| ADRs | Locked design decisions and rationale |
| Service boundaries plan | Directory ownership, runtime boundaries, and allowed write scopes |
| Contract freeze plan | v1 contract shape and compatibility rules |
| Milestone operating model | How rewrite milestones are decomposed, staffed, and reported |
| Milestone plan | Current milestone workstreams, waves, effort, and remaining backlog |
| Parallel execution plan | How multiple agents can work safely in parallel |
| Validation and cutover plan | How the new substrate is proven and flipped into authority |
| Collector authoring guide | How new ingestors fit the shared scope/generation/fact/reducer contract |
| Cloud validation runbook | Hosted verification order and operator evidence checks |
| Architecture and traversal references | Canonical end-to-end flow, ownership boundaries, and repair-path limits |
| Relationship-mapping observability appendix | The traversal appendix and observability examples for the relationship map |
| Write-plane conversion cutover | Chunk-by-chunk Python-to-Go deployment surface cutover |
| Ownership completion plan | Resolution domain, operational surface, and recovery endpoint migration to Go |
| Terraform provider schema checklist | Runtime parity checklist for the schema-driven Terraform evidence seam |
| Terraform provider schema implementation plan | Chunked execution plan for moving provider-schema runtime ownership to Go |

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
- the service boundaries, contract freeze, milestone, parallel execution, and
  validation plans are present and cross-linked
- future work can be assigned without guessing where logic belongs

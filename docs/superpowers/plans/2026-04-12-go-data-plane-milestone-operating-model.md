# Go Data Plane Milestone Operating Model

This document defines how rewrite milestones should be shaped, staffed, and
reported on this branch.

The goal is to stop turning major platform work into disconnected micro-slices
and instead execute **whole architectural outcomes** with clear ownership and
repeatable proof.

## Why This Model Exists

The rewrite is large enough that we need parallel execution, but broad enough
that uncontrolled parallelism creates drift, rework, and false confidence.

This operating model exists to keep each milestone:

- large enough to represent a real system outcome
- small enough to validate locally and in the cloud test environment
- decomposed by subsystem ownership instead of helper-by-helper edits
- explainable to future workers without rereading chat history

## Milestone Shape

Each rewrite milestone must be defined as one coherent platform outcome.

Examples of good milestone shapes:

- native Git collector cutover with end-to-end operability
- source projector and reducer domain authority flip for one proof domain
- operator/admin runtime status surfaces across all long-running services
- deterministic local and cloud validation gate for one authority boundary

Examples of bad milestone shapes:

- add one helper
- split one file
- wire one extra metric without owning the operator story
- land one internal seam without the validation or admin contract around it

## Required Sections For Every Milestone

Every milestone plan must include:

1. Summary
2. Architectural outcome
3. In-scope and out-of-scope work
4. Workstreams with owned paths
5. Subagent assignment model
6. Dependency waves
7. Acceptance criteria
8. Local validation commands
9. Cloud proof requirements when applicable
10. Backlog split into completed, current, and remaining work

No milestone is considered executable until these sections exist in the repo.

## Workstream Rules

Each milestone should usually have between **3 and 5 workstreams**.

Each workstream should own a **vertical subsystem outcome**, not a thin edit
category.

Good workstream examples:

- contract and architecture lock
- native collector implementation
- projector and persistence path
- operability and admin surface
- end-to-end validation and proof harness

Bad workstream examples:

- tests only
- helper refactors
- comments and docs
- one file per agent

## Subagent Model

The main agent stays responsible for:

- architecture decisions
- shared contract review
- integration order
- conflict resolution
- final verification
- commit, push, PR, and milestone reporting

Subagents should own **disjoint write scopes** and one full workstream each.

Recommended default staffing:

- 1 main agent
- 2 to 4 worker subagents

Do not spawn more workers unless the workstreams are truly independent and the
contracts are already frozen.

## Dependency Waves

Milestones should run in waves instead of free-form parallel work.

### Wave 0: Contract lock

Outputs:

- ADRs and plan docs updated
- interfaces frozen for the milestone
- acceptance criteria written

Parallel implementation does not begin before this wave is done.

### Wave 1: Core implementation

Outputs:

- the primary subsystem workstreams land in parallel
- each workstream has focused tests and local proof

Typical staffing:

- collector worker
- projector/persistence worker
- operability or validation worker

### Wave 2: Integration

Outputs:

- workstreams are stitched together
- compatibility and drift issues are resolved
- end-to-end local validation passes

### Wave 3: Proof and report

Outputs:

- final local validation passes
- docs are updated to match reality
- remaining backlog is reported by workstream and effort

## Effort Scale

Use these effort bands in milestone plans:

- `Small`: 1 focused slice, limited file ownership, low integration risk
- `Medium`: several files or one subsystem, moderate contract touch points
- `Large`: multi-package subsystem, important integration boundary, needs full validation
- `XL`: broad milestone umbrella; should usually be broken into multiple workstreams

Milestones should be made of several `Medium` and `Large` workstreams, not many
`Small` ones.

## Completion Rules

A workstream is only complete when all of the following are true:

- code is implemented without placeholder logic
- tests for the owned contract pass
- relevant docs are updated
- local validation for that workstream passes
- the result is reported with what changed, what was verified, and what remains

A milestone is only complete when:

- all workstreams satisfy their completion rules
- the end-to-end validation layer passes
- operator/admin visibility exists for the new behavior
- remaining legacy bridge behavior is explicitly documented

## Reporting Rules

After each commit and push, milestone reporting should include:

- what workstream was advanced
- what exact validation passed
- what remains in the milestone
- effort for each remaining workstream
- whether the next work is parallelizable or blocked

This branch should never rely on “we probably finished most of it.”

## Anti-Patterns

Avoid these execution patterns:

- splitting one subsystem across multiple workers without a frozen contract
- making one worker “tests only” while another edits the same subsystem
- landing scaffolding and calling the workstream complete
- hiding milestone risk behind green unit tests only
- deferring docs until after multiple implementation waves
- using the legacy path as an excuse to skip the new operator/admin story

## Standard Milestone Template

Every new milestone plan should use this outline:

```md
# <Milestone Name>

## Summary

## Architectural Outcome

## Scope

### In Scope

### Out Of Scope

## Workstreams

### Workstream A: <name>
- Purpose
- Owned paths
- Deliverables
- Acceptance criteria
- Effort

### Workstream B: <name>
...

## Subagent Assignment

## Dependency Waves

## Validation

## Current Status

### Completed

### In Flight

### Remaining
```

## Branch Rule

For the rewrite branch, each milestone should get its own milestone plan file.

The plan file must be updated when:

- a workstream is completed
- a dependency wave changes
- a major acceptance criterion changes
- remaining effort is materially re-estimated

This is the mechanism we should use for each milestone on this branch.

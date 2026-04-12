# Go Data Plane Milestone Operating Model

This document explains how the rewrite should be decomposed, staffed, and
reported so future workers can keep moving without re-litigating the branch
shape.

## Purpose

The rewrite is not a list of tiny tickets. Each milestone should represent one
observable architecture outcome that can be validated locally before the next
wave begins.

Use this operating model when you need to decide:

- what belongs in the current milestone
- how much work a slice should contain
- which validation gate proves the slice
- what needs to be documented before the slice is complete

## Milestone Anatomy

Every milestone should have:

1. one architecture outcome
2. two to four workstreams
3. explicit owned paths
4. a validation command or small command set
5. a doc update requirement
6. a short report describing what remains

If a milestone does not have those pieces, it is too vague to delegate.

## Effort Bands

Use these bands to keep work meaningful without making it monolithic:

- `Small`: a focused doc or contract update, usually one owner and one
  validation command
- `Medium`: a bounded runtime or query change with one integration proof
- `Large`: a full service-slice or contract-family change with multiple tests
- `Extra Large`: only when the milestone outcome is truly cross-cutting and
  cannot be split without losing architectural meaning

Prefer a `Large` milestone with a few clear workstreams over a dozen `Small`
patches that do not produce a visible platform outcome.

## Sequencing Rules

- lock the architecture and contract shape first
- build the substrate before adding more collectors
- prove one bounded path locally before claiming rewrite readiness
- keep read-plane compatibility while the data plane changes underneath it
- do not let validation depend on a future service shape that has not landed

## Validation Rules

Every milestone should prove four things:

- the code compiles and the targeted tests pass
- the docs explain the new boundary or contract
- the runtime/admin/status surface matches the service shape
- the work can be explained as a flow from source to canonical state

The default validation stack is:

- focused unit tests
- focused integration tests
- docs build or lint where docs changed
- one local runtime proof command when the milestone touches service behavior

## Slice Reporting Format

After each slice, report in the same order:

- what milestone and workstream changed
- what owned paths were touched
- what validation command passed
- what remains blocked
- whether the change is final architecture or a temporary bridge

## Parallelism Guidance

When multiple workers are available:

- give each worker one workstream or one bounded validation slice
- avoid overlapping root docs and generated contract files
- keep the main agent on integration, review, and milestone reporting
- do not split a single architectural decision across multiple workers

## Default Milestone Pattern

For this branch, the preferred sequence is:

1. lock contracts and operator rules
2. deliver one native runtime proof path
3. add scope-first ingestion and incremental refresh
4. separate canonical truth and reducer ownership
5. retire the legacy write seam
6. expand to new collectors on the same contract

That pattern should stay visible in the milestone docs, the public roadmap, and
the runtime/telemetry guidance so future workers know what phase they are in.

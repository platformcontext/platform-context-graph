# Go Data Plane Contract Freeze Plan

This document defines the first contract set that must be frozen before major
implementation fan-out begins.

The contract set is schema-first, versioned, and designed to support multiple
services without forcing transport choices too early.

## Contract Families

### Scope contracts

Package: `platform_context_graph.data_plane.scope.v1`

Required messages:

- `IngestionScope`
- `ScopeGeneration`

Required fields:

- stable identifiers
- source system and scope kind
- parent scope reference when nested
- collector kind
- partition key
- observed and ingested timestamps
- generation status
- trigger kind and freshness hint

### Fact contracts

Package: `platform_context_graph.data_plane.facts.v1`

Required messages:

- `FactEnvelope`
- `FactRef`

Required fields:

- fact identifier
- scope and generation identifiers
- fact kind
- stable fact key
- observed timestamp
- payload
- deletion or tombstone indicator
- source-local reference metadata

### Queue contracts

Package: `platform_context_graph.data_plane.queue.v1`

Required messages:

- `WorkItem`
- `RetryState`
- `FailureRecord`

Required fields:

- work-item identifier
- scope and generation identifiers
- stage
- domain
- attempt count
- status
- claim and visibility timing
- failure classification and message

### Reducer contracts

Package: `platform_context_graph.data_plane.reducer.v1`

Required messages:

- `ReducerIntent`
- `ReducerResult`

Required fields:

- intent identifier
- scope and generation identifiers
- reducer domain
- cause
- priority
- scheduler timestamps
- affected entity keys when known
- result status and evidence summary

### Projection contracts

Package: `platform_context_graph.data_plane.projection.v1`

Required messages:

- `ProjectionResult`
- `CanonicalWriteRecord`

Required fields:

- projector identity
- scope and generation identifiers
- write target
- counts and timing
- status
- partial or unresolved notes

## Compatibility Rules

- v1 packages are additive-only once frozen.
- Field numbers must never be reused.
- Removed fields must be marked reserved.
- Semantic meaning changes require a new field or a new version.
- Optional transport is allowed, but payload meaning may not depend on one
  transport implementation.

## Storage And Transport Assumptions

- Protobuf is the contract format for durable payloads and shared interfaces.
- The first milestone does not require gRPC or another network RPC layer.
- Services may communicate through durable storage and queues first, as long as
  the shared payload contract is versioned and generated from the same schema.

## Naming Contract

### Metric dimensions

- `scope_id`
- `scope_kind`
- `source_system`
- `generation_id`
- `collector_kind`
- `domain`
- `partition_key`

### Span names

- `collector.observe`
- `scope.assign`
- `fact.emit`
- `projector.run`
- `reducer_intent.enqueue`
- `reducer.run`
- `canonical.write`

### Log keys

- `scope_id`
- `scope_kind`
- `source_system`
- `generation_id`
- `collector_kind`
- `domain`
- `partition_key`
- `request_id`
- `failure_class`

## Freeze Process

The contract freeze is complete when:

- the package list above exists in `proto/`
- initial generated code is checked in or reproducibly generated
- the compatibility and naming rules are documented in the repo
- any change to these contracts requires an explicit versioning note in the
  relevant plan or ADR

# ADR: Logical Workload Spine

**Status:** Accepted

## Context

PCG is not only a code and infrastructure graph. It also needs to model the
logical things an organization operates: APIs, services, jobs, ETL pipelines,
workers, schedulers, stream consumers, and serverless processors.

If each runtime shape creates its own unrelated entity model, the graph will
fracture. If every data or analytics concept is forced into infrastructure
identity, the graph will also become confusing.

## Decision

PCG will use a logical-first workload spine built from:

- `Workload`
- `WorkloadInstance`

`Workload` is the logical thing the organization owns. `WorkloadInstance` is
the environment-specific or runtime-specific realization of that workload.

Workload subtypes include:

- service
- API
- ETL pipeline
- scheduled job
- batch worker
- stream consumer
- controller
- serverless processor

`DataAsset` and `AnalyticsModel` remain separate first-class concepts. They do
not collapse into workloads, but they can relate to workloads through
ownership, production, consumption, or dependency edges.

## Why This Choice

- It gives PCG one durable way to talk about logical business systems.
- It keeps ETL and analytics systems inside the platform graph instead of
  treating them as second-class exceptions.
- It avoids coupling runtime deployment form to logical identity.
- It keeps data lineage and workload topology connected without flattening them
  into one concept.

## Consequences

Positive:

- Platform, application, and data teams can reason about the same graph.
- A workload can be traced across Kubernetes, Lambda, Airflow, or other
  runtimes without changing its logical identity.
- Data-producing or data-consuming jobs can stay connected to both workload and
  data-asset views.

Tradeoffs:

- Reducers must perform workload reconciliation carefully.
- Query surfaces need to explain logical versus runtime instance views.

## Implementation Guidance

- Workload reducers should own logical workload identity.
- Collector and projector stages should emit runtime-local evidence and hints,
  not attempt cross-runtime workload unification inline.
- Data and analytics entities should connect to workloads through explicit edge
  types such as ownership, produces, consumes, runs, or powers.
- ETL and job systems must be modeled as workload subtypes from the start, not
  as future exceptions.

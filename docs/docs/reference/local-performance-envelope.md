# Local Performance Envelope

This document defines the target envelope for the lightweight local host.

## Goals

The local host should be useful on a normal developer laptop, not only on ideal
hardware or empty repos.

## Initial Targets

Reference hardware:

- Apple Silicon laptop with 16 GB RAM
- or mid-range x86 laptop with 4+ cores and 16 GB RAM

- cold start: under 5 seconds
- warm restart: under 2 seconds
- exact symbol lookup p95: under 500 ms
- content search p95: under 800 ms
- complexity query p95: under 1500 ms
- single-file reindex to visible search update: under 2 seconds
- initial index of an active repo: document and measure against the capability
  matrix scope sizes
- idle memory budget: document and measure
- active indexing memory budget: document and measure

## Workload Shapes

Targets should be tracked at least for:

- active repo
- active monofolder

The capability matrix should tie latency expectations to these scope sizes.

Warm restart means the same workspace data root is reused and no full reindex is
required. Cold start means starting the host from a stopped state with no warm
processes already attached.

## Backpressure Expectations

- fsnotify events must be coalesced and debounced
- parse and projection pools must be bounded
- the runtime must prefer bounded lag over unbounded CPU or memory growth

## Review Rule

If the local host misses these targets, the docs and matrix should reflect the
actual supported envelope instead of hiding the miss.

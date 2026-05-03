# Telemetry

`telemetry` owns PCG's OpenTelemetry contract, metric instruments, span names,
structured log keys, and shared runtime attributes.

Runtime changes should make operator diagnosis easier. Metrics need bounded
labels, traces need useful span names, and logs should carry enough context to
debug a stalled indexing run.

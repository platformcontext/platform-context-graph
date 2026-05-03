# Projector

`projector` owns source-local projection work. It turns committed facts into
canonical graph writes and publishes readiness for reducer-owned shared domains.

Projection code must be idempotent. Queue retries, duplicate claims, and partial
graph writes should converge on the same graph truth instead of creating hidden
second paths.

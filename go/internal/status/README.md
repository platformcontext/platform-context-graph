# Status

`status` owns the shared reporting shape for pipeline state, backlog, health,
and completeness.

Keep the CLI, HTTP admin, and runtime status views aligned. Operators should not
need a different mental model for each PCG service.

# Reducer

`reducer` owns cross-domain materialization, queued repair, and shared projection
after source-local facts have been committed.

Reducer changes need careful proof. Track the raw evidence, admitted candidates,
projected rows, graph writes, and query surfaces before changing ordering,
admission, retries, or backend-specific behavior.

# Cross-Phase EntityNotFound Race — Evidence Appendix

Companion evidence for
[ADR: Cross-Phase EntityNotFound Race](2026-04-16-cross-phase-entity-not-found-race.md).

## Cypher Evidence

### Phase A retraction WITH generation filter (correct)

```cypher
-- Files
MATCH (f:File)
WHERE f.repo_id = $repo_id
  AND f.evidence_source = 'projector/canonical'
  AND f.generation_id <> $generation_id
DETACH DELETE f

-- Code entities (same pattern for infra, terraform, cloudformation, sql, data)
MATCH (n)
WHERE n.repo_id = $repo_id
  AND n.evidence_source = 'projector/canonical'
  AND n.generation_id <> $generation_id
  AND (n:Function OR n:Class OR ...)
DETACH DELETE n
```

### Phase A retraction WITHOUT generation filter (bugs)

```cypher
-- Directories (canonical_node_cypher.go:42-44)
MATCH (d:Directory)
WHERE d.repo_id = $repo_id
DETACH DELETE d

-- Parameters (canonical_node_cypher.go:46-48)
MATCH (p:Parameter)
WHERE p.path IN $file_paths
  AND p.evidence_source = 'projector/canonical'
DETACH DELETE p
```

### Semantic entity retraction WITHOUT generation filter (still too broad)

```cypher
-- semantic_entity.go:243-246
MATCH (n:Annotation|Typedef|TypeAlias|TypeAnnotation|Component|Module|
       ImplBlock|Protocol|ProtocolImplementation|Variable|Function)
WHERE n.repo_id IN $repo_ids
  AND n.evidence_source = $evidence_source
DETACH DELETE n
```

### Semantic entity upsert depends on File MATCH

```cypher
-- semantic_entity.go:15-16 (repeated for all 11 entity types)
UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Annotation {uid: row.entity_id})
SET ...
MERGE (f)-[:CONTAINS]->(n)
```

### Semantic entity writes are grouped atomically on the reducer path

The reducer-side semantic entity writer builds one statement group and prefers
`ExecuteGroup(...)` when supported by the executor:

```go
// semantic_entity.go
if ge, ok := w.executor.(GroupExecutor); ok {
    if err := ge.ExecuteGroup(ctx, stmts); err != nil { ... }
}
```

This means the semantic retract is still too broad, but it is not the clearest
same-generation observation-window culprit on the deployed reducer path.

### Code call upsert depends on entity MATCH

```cypher
-- canonical.go:155-157
UNWIND $rows AS row
MATCH (source:Function|Class|File {uid: coalesce(row.caller_entity_id, row.source_entity_id)})
MATCH (target:Function|Class|File {uid: coalesce(row.callee_entity_id, row.target_entity_id)})
MERGE (source)-[rel:CALLS]->(target)
```

## Raw Log Evidence

### Sample EntityNotFound error (representative)

```json
{
  "timestamp": "2026-04-16T20:16:39.750683735Z",
  "severity_text": "ERROR",
  "message": "reducer execution failed",
  "domain": "semantic_entity_materialization",
  "partition_key": "content-entity:e_2022238d65ca",
  "queue": "reducer",
  "status": "failed",
  "duration_seconds": 0.217204218,
  "worker_id": 3,
  "pipeline_phase": "reduction",
  "failure_class": "reducer_failure",
  "error": "write semantic entities: write semantic entities: Neo4jError: Neo.ClientError.Statement.EntityNotFound (Unable to load NODE 4:1d852d49-e974-435c-bf22-a4df7a621769:5087.)"
}
```

### Error classification query results

```
# Neo4j error types (from resolution-engine logs)
   1053 Neo4jError: Neo.ClientError.Statement.EntityNotFound
    205 Neo4jError: Neo.TransientError.Transaction.DeadlockDetected

# Errors by domain
   1184 "domain":"semantic_entity_materialization"
     75 "domain":"code_call_materialization"

# Cross-tabulation: EntityNotFound by domain
    990 semantic_entity_materialization
     71 code_call_materialization

# Cross-tabulation: DeadlockDetected by domain
    216 semantic_entity_materialization
      4 code_call_materialization

# Error time range
First: 2026-04-16T20:16:39Z
Last:  2026-04-16T21:49:24Z
Duration: 93 minutes (errors distributed throughout)
```

### Why errors are terminal (code path)

```go
// reducer/intent.go:81-96
type RetryableError interface {
    error
    Retryable() bool
}

func IsRetryable(err error) bool {
    var retryable RetryableError
    if !errors.As(err, &retryable) {
        return false  // ← plain fmt.Errorf errors return false here
    }
    return retryable.Retryable()
}

// storage/postgres/reducer_queue.go:434
if q.retryable(cause, intent.AttemptCount) {
    failureClass = "reducer_retryable"  // ← never reached for these errors
    // ... re-enqueue with backoff
} else {
    // ... mark as terminal failure
}
```

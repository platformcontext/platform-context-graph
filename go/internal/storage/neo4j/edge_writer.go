package neo4j

import (
	"context"
	"fmt"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

// EdgeWriter implements reducer.SharedProjectionEdgeWriter by dispatching
// domain-specific canonical Cypher statements through a Neo4j Executor.
// Writes are batched using UNWIND for efficiency.
type EdgeWriter struct {
	executor  Executor
	BatchSize int
}

// NewEdgeWriter returns an EdgeWriter backed by the given Executor.
// A batchSize of 0 or less uses DefaultBatchSize (500).
func NewEdgeWriter(executor Executor, batchSize int) *EdgeWriter {
	return &EdgeWriter{executor: executor, BatchSize: batchSize}
}

func (w *EdgeWriter) batchSize() int {
	if w.BatchSize <= 0 {
		return DefaultBatchSize
	}
	return w.BatchSize
}

// WriteEdges writes canonical domain edges for the given rows using batched
// UNWIND statements. Rows with empty required MATCH fields are skipped to
// avoid silent failures in the batch.
func (w *EdgeWriter) WriteEdges(
	ctx context.Context,
	domain string,
	rows []reducer.SharedProjectionIntentRow,
	evidenceSource string,
) error {
	if len(rows) == 0 {
		return nil
	}
	if w.executor == nil {
		return fmt.Errorf("edge writer executor is required")
	}

	cypher, err := batchCypherForDomain(domain)
	if err != nil {
		return err
	}

	var validRows []map[string]any
	for _, row := range rows {
		rowMap, ok := buildRowMap(domain, row, evidenceSource)
		if !ok {
			continue
		}
		validRows = append(validRows, rowMap)
	}

	if len(validRows) == 0 {
		return nil
	}

	return w.executeBatched(ctx, cypher, validRows)
}

// executeBatched executes batched UNWIND operations, mirroring
// Adapter.executeBatched in writer.go.
func (w *EdgeWriter) executeBatched(ctx context.Context, cypher string, rows []map[string]any) error {
	bs := w.batchSize()
	for start := 0; start < len(rows); start += bs {
		end := start + bs
		if end > len(rows) {
			end = len(rows)
		}
		if err := w.executor.Execute(ctx, Statement{
			Operation:  OperationCanonicalUpsert,
			Cypher:     cypher,
			Parameters: map[string]any{"rows": rows[start:end]},
		}); err != nil {
			return err
		}
	}
	return nil
}

// batchCypherForDomain returns the batched UNWIND Cypher template for the
// given shared projection domain.
func batchCypherForDomain(domain string) (string, error) {
	switch domain {
	case reducer.DomainPlatformInfra:
		return batchCanonicalInfrastructurePlatformUpsertCypher, nil
	case reducer.DomainRepoDependency:
		return batchCanonicalRepoDependencyUpsertCypher, nil
	case reducer.DomainWorkloadDependency:
		return batchCanonicalWorkloadDependencyUpsertCypher, nil
	case reducer.DomainCodeCalls:
		return batchCanonicalCodeCallUpsertCypher, nil
	default:
		return "", fmt.Errorf("unsupported domain for write: %q", domain)
	}
}

// buildRowMap converts a SharedProjectionIntentRow into a flat parameter map
// suitable for UNWIND batching. Returns false if required MATCH fields for the
// domain are empty, indicating the row should be skipped.
func buildRowMap(
	domain string,
	row reducer.SharedProjectionIntentRow,
	evidenceSource string,
) (map[string]any, bool) {
	switch domain {
	case reducer.DomainPlatformInfra:
		repoID := payloadString(row.Payload, "repo_id")
		platformID := payloadString(row.Payload, "platform_id")
		if repoID == "" || platformID == "" {
			return nil, false
		}
		return map[string]any{
			"repo_id":              repoID,
			"platform_id":          platformID,
			"platform_name":        payloadString(row.Payload, "platform_name"),
			"platform_kind":        payloadString(row.Payload, "platform_kind"),
			"platform_provider":    payloadString(row.Payload, "platform_provider"),
			"platform_environment": payloadString(row.Payload, "platform_environment"),
			"platform_region":      payloadString(row.Payload, "platform_region"),
			"platform_locator":     payloadString(row.Payload, "platform_locator"),
			"evidence_source":      evidenceSource,
		}, true

	case reducer.DomainRepoDependency:
		repoID := payloadString(row.Payload, "repo_id")
		targetRepoID := payloadString(row.Payload, "target_repo_id")
		if repoID == "" || targetRepoID == "" {
			return nil, false
		}
		return map[string]any{
			"repo_id":         repoID,
			"target_repo_id":  targetRepoID,
			"evidence_source": evidenceSource,
		}, true

	case reducer.DomainWorkloadDependency:
		workloadID := payloadString(row.Payload, "workload_id")
		targetWorkloadID := payloadString(row.Payload, "target_workload_id")
		if workloadID == "" || targetWorkloadID == "" {
			return nil, false
		}
		return map[string]any{
			"workload_id":        workloadID,
			"target_workload_id": targetWorkloadID,
			"evidence_source":    evidenceSource,
		}, true

	case reducer.DomainCodeCalls:
		callerEntityID := payloadString(row.Payload, "caller_entity_id")
		calleeEntityID := payloadString(row.Payload, "callee_entity_id")
		if callerEntityID == "" || calleeEntityID == "" {
			return nil, false
		}
		rowMap := map[string]any{
			"caller_entity_id": callerEntityID,
			"callee_entity_id": calleeEntityID,
			"evidence_source":  evidenceSource,
		}
		if callKind := payloadString(row.Payload, "call_kind"); callKind != "" {
			rowMap["call_kind"] = callKind
		}
		return rowMap, true

	default:
		return nil, false
	}
}

// RetractEdges retracts canonical domain edges for the given rows. Retraction
// collects repo IDs from all rows and executes one batched DELETE statement.
func (w *EdgeWriter) RetractEdges(
	ctx context.Context,
	domain string,
	rows []reducer.SharedProjectionIntentRow,
	evidenceSource string,
) error {
	if len(rows) == 0 {
		return nil
	}
	if w.executor == nil {
		return fmt.Errorf("edge writer executor is required")
	}

	repoIDs := collectRepoIDs(rows)
	stmt, err := buildRetractStatement(domain, repoIDs, evidenceSource)
	if err != nil {
		return err
	}

	return w.executor.Execute(ctx, stmt)
}

func buildRetractStatement(
	domain string,
	repoIDs []string,
	evidenceSource string,
) (Statement, error) {
	switch domain {
	case reducer.DomainPlatformInfra:
		return BuildRetractInfrastructurePlatformEdges(repoIDs, evidenceSource), nil
	case reducer.DomainRepoDependency:
		return BuildRetractRepoDependencyEdges(repoIDs, evidenceSource), nil
	case reducer.DomainWorkloadDependency:
		return BuildRetractWorkloadDependencyEdges(repoIDs, evidenceSource), nil
	case reducer.DomainCodeCalls:
		return BuildRetractCodeCallEdges(repoIDs, evidenceSource), nil
	default:
		return Statement{}, fmt.Errorf("unsupported domain for retract: %q", domain)
	}
}

func collectRepoIDs(rows []reducer.SharedProjectionIntentRow) []string {
	seen := make(map[string]struct{}, len(rows))
	var result []string
	for _, row := range rows {
		repoID := row.RepositoryID
		if repoID == "" {
			repoID = payloadString(row.Payload, "repo_id")
		}
		if repoID == "" {
			continue
		}
		if _, ok := seen[repoID]; ok {
			continue
		}
		seen[repoID] = struct{}{}
		result = append(result, repoID)
	}
	return result
}

func payloadString(payload map[string]any, key string) string {
	if payload == nil {
		return ""
	}
	v, ok := payload[key]
	if !ok {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return s
}

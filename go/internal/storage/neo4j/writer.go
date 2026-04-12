// Package neo4j provides a source-local graph write substrate for Neo4j-backed
// projector output.
//
// The supported subset is intentionally narrow: source-local node upserts and
// tombstone deletes keyed by scope, generation, and record. It does not model
// edges, reducer-owned canonical domains, or cross-source reconciliation.
package neo4j

import (
	"context"
	"fmt"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/graph"
)

const (
	upsertNodeCypher = `MERGE (n:SourceLocalRecord {scope_id: $scope_id, generation_id: $generation_id, record_id: $record_id})
SET n.source_system = $source_system,
    n.kind = $kind,
    n.attributes = $attributes,
    n.deleted = false`

	deleteNodeCypher = `MATCH (n:SourceLocalRecord {scope_id: $scope_id, generation_id: $generation_id, record_id: $record_id})
DELETE n`
)

// Operation identifies the supported source-local Neo4j write type.
type Operation string

const (
	// OperationUpsertNode writes or refreshes one source-local node.
	OperationUpsertNode Operation = "upsert_node"
	// OperationDeleteNode removes one source-local node tombstoned by the source.
	OperationDeleteNode Operation = "delete_node"
)

// Statement captures one executable Neo4j Cypher statement.
type Statement struct {
	Operation  Operation
	Cypher     string
	Parameters map[string]any
}

// Plan is the deterministic source-local write plan for one materialization.
type Plan struct {
	ScopeID      string
	GenerationID string
	Statements   []Statement
}

// Executor executes one Cypher statement.
type Executor interface {
	Execute(context.Context, Statement) error
}

// Adapter writes source-local graph records through an Executor.
type Adapter struct {
	Executor Executor
}

// Write builds and executes the source-local write plan for one materialization.
func (a Adapter) Write(ctx context.Context, materialization graph.Materialization) (graph.Result, error) {
	plan, err := BuildPlan(materialization)
	if err != nil {
		return graph.Result{}, err
	}

	if a.Executor == nil {
		if len(plan.Statements) == 0 {
			return resultFor(materialization), nil
		}
		return graph.Result{}, fmt.Errorf("neo4j executor is required when source-local statements are present")
	}

	for i := range plan.Statements {
		if err := a.Executor.Execute(ctx, plan.Statements[i]); err != nil {
			return graph.Result{}, fmt.Errorf("execute source-local graph statement %d: %w", i, err)
		}
	}

	return resultFor(materialization), nil
}

// BuildPlan converts a source-local graph materialization into Neo4j statements.
func BuildPlan(materialization graph.Materialization) (Plan, error) {
	if err := validateMaterialization(materialization); err != nil {
		return Plan{}, err
	}

	plan := Plan{
		ScopeID:      materialization.ScopeID,
		GenerationID: materialization.GenerationID,
	}

	for i := range materialization.Records {
		record := materialization.Records[i].Clone()
		statement, err := buildStatement(materialization, record, i)
		if err != nil {
			return Plan{}, err
		}
		if statement.Operation == "" {
			continue
		}
		plan.Statements = append(plan.Statements, statement)
	}

	return plan, nil
}

func buildStatement(materialization graph.Materialization, record graph.Record, index int) (Statement, error) {
	if err := validateRecord(record, index); err != nil {
		return Statement{}, err
	}

	if record.Deleted {
		return Statement{
			Operation:  OperationDeleteNode,
			Cypher:     deleteNodeCypher,
			Parameters: deleteParameters(materialization, record),
		}, nil
	}

	if err := validateUpsertRecord(record, index); err != nil {
		return Statement{}, err
	}

	return Statement{
		Operation:  OperationUpsertNode,
		Cypher:     upsertNodeCypher,
		Parameters: upsertParameters(materialization, record),
	}, nil
}

func validateMaterialization(materialization graph.Materialization) error {
	if strings.TrimSpace(materialization.ScopeID) == "" {
		return fmt.Errorf("scope_id must not be blank")
	}
	if strings.TrimSpace(materialization.GenerationID) == "" {
		return fmt.Errorf("generation_id must not be blank")
	}
	if strings.TrimSpace(materialization.SourceSystem) == "" {
		return fmt.Errorf("source_system must not be blank")
	}

	return nil
}

func validateRecord(record graph.Record, index int) error {
	if strings.TrimSpace(record.RecordID) == "" {
		return fmt.Errorf("record %d record_id must not be blank", index)
	}

	return nil
}

func validateUpsertRecord(record graph.Record, index int) error {
	if strings.TrimSpace(record.Kind) == "" {
		return fmt.Errorf("record %d kind must not be blank for source-local upsert", index)
	}

	return nil
}

func upsertParameters(materialization graph.Materialization, record graph.Record) map[string]any {
	attributes := cloneStringMap(record.Attributes)
	if attributes == nil {
		attributes = map[string]string{}
	}

	return map[string]any{
		"scope_id":      materialization.ScopeID,
		"generation_id": materialization.GenerationID,
		"source_system": materialization.SourceSystem,
		"record_id":     record.RecordID,
		"kind":          record.Kind,
		"attributes":    attributes,
	}
}

func deleteParameters(materialization graph.Materialization, record graph.Record) map[string]any {
	return map[string]any{
		"scope_id":      materialization.ScopeID,
		"generation_id": materialization.GenerationID,
		"record_id":     record.RecordID,
	}
}

func resultFor(materialization graph.Materialization) graph.Result {
	result := graph.Result{
		ScopeID:      materialization.ScopeID,
		GenerationID: materialization.GenerationID,
		RecordCount:  len(materialization.Records),
	}
	for i := range materialization.Records {
		if materialization.Records[i].Deleted {
			result.DeletedCount++
		}
	}

	return result
}

func cloneStringMap(input map[string]string) map[string]string {
	if input == nil {
		return nil
	}

	cloned := make(map[string]string, len(input))
	for key, value := range input {
		cloned[key] = value
	}

	return cloned
}

package postgres

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

type recordingGraphWriter struct {
	calls []graph.Materialization
}

func (w *recordingGraphWriter) Write(_ context.Context, materialization graph.Materialization) (graph.Result, error) {
	w.calls = append(w.calls, materialization.Clone())
	return graph.Result{RecordCount: len(materialization.Records)}, nil
}

type recordingContentWriter struct {
	calls []content.Materialization
}

func (w *recordingContentWriter) Write(_ context.Context, materialization content.Materialization) (content.Result, error) {
	w.calls = append(w.calls, materialization.Clone())
	return content.Result{RecordCount: len(materialization.Records)}, nil
}

type proofDomainDB struct {
	now           time.Time
	state         proofState
	reducerClaims int
	reducerAcked  int
}

type proofState struct {
	scopes      map[string]scope.IngestionScope
	generations map[string]scope.ScopeGeneration
	facts       map[string]facts.Envelope
	workItems   map[string]proofWorkItem
}

type proofScopeRow struct {
	scope      scope.IngestionScope
	generation scope.ScopeGeneration
}

type proofWorkItem struct {
	workItemID   string
	stage        string
	domain       string
	status       string
	scopeID      string
	generationID string
	leaseOwner   string
	visibleAt    time.Time
	createdAt    time.Time
	updatedAt    time.Time
	claimUntil   time.Time
	payload      []byte
}

func newProofDomainDB(t *testing.T, now time.Time) *proofDomainDB {
	t.Helper()

	return &proofDomainDB{
		now: now.UTC(),
		state: proofState{
			scopes:      make(map[string]scope.IngestionScope),
			generations: make(map[string]scope.ScopeGeneration),
			facts:       make(map[string]facts.Envelope),
			workItems:   make(map[string]proofWorkItem),
		},
	}
}

func (db *proofDomainDB) Begin(context.Context) (Transaction, error) {
	return &proofDomainTx{
		db: db,
		state: proofState{
			scopes:      cloneScopes(db.state.scopes),
			generations: cloneGenerations(db.state.generations),
			facts:       cloneFacts(db.state.facts),
			workItems:   cloneWorkItems(db.state.workItems),
		},
	}, nil
}

func (db *proofDomainDB) ExecContext(_ context.Context, query string, args ...any) (sql.Result, error) {
	switch {
	case strings.Contains(query, "WHERE stage = 'projector'") && strings.Contains(query, "status = 'succeeded'"):
		if len(args) != 4 {
			return nil, fmt.Errorf("projector ack args = %d, want 4", len(args))
		}
		return db.updateWorkItemStatus("projector", args[1].(string), args[2].(string), args[3].(string), "succeeded")
	case strings.Contains(query, "WHERE stage = 'projector'") && strings.Contains(query, "status = 'failed'"):
		if len(args) != 7 {
			return nil, fmt.Errorf("projector fail args = %d, want 7", len(args))
		}
		return db.updateWorkItemStatus("projector", args[4].(string), args[5].(string), args[6].(string), "failed")
	case strings.Contains(query, "stage = 'reducer'") && strings.Contains(query, "SET status = 'succeeded'"):
		if len(args) != 3 {
			return nil, fmt.Errorf("reducer ack args = %d, want 3", len(args))
		}
		return db.updateWorkItemStatusByID(args[1].(string), args[2].(string), "succeeded")
	case strings.Contains(query, "stage = 'reducer'") && strings.Contains(query, "SET status = 'failed'"):
		if len(args) != 6 {
			return nil, fmt.Errorf("reducer fail args = %d, want 6", len(args))
		}
		return db.updateWorkItemStatusByID(args[4].(string), args[5].(string), "failed")
	case strings.Contains(query, "INSERT INTO fact_work_items") && strings.Contains(query, "'reducer'"):
		payload, err := unmarshalPayload(args[5].([]byte))
		if err != nil {
			return nil, err
		}
		workItem := proofWorkItem{
			workItemID:   args[0].(string),
			stage:        "reducer",
			domain:       args[3].(string),
			status:       "pending",
			scopeID:      args[1].(string),
			generationID: args[2].(string),
			visibleAt:    args[4].(time.Time).UTC(),
			createdAt:    args[4].(time.Time).UTC(),
			updatedAt:    args[4].(time.Time).UTC(),
			payload:      args[5].([]byte),
		}
		if len(payload) > 0 {
			workItem.payload = args[5].([]byte)
		}
		db.state.workItems[workItem.workItemID] = workItem
		return proofResult{}, nil
	default:
		return nil, fmt.Errorf("unexpected exec query: %s", query)
	}
}

func (db *proofDomainDB) QueryContext(_ context.Context, query string, args ...any) (Rows, error) {
	switch {
	case strings.Contains(query, "FROM fact_records"):
		if len(args) != 2 {
			return nil, fmt.Errorf("list facts args = %d, want 2", len(args))
		}
		scopeID, _ := args[0].(string)
		generationID, _ := args[1].(string)
		return newProofRows(proofFactRows(db.state.facts, scopeID, generationID)), nil
	case strings.Contains(query, "stage = 'projector'"):
		if len(args) != 3 {
			return nil, fmt.Errorf("projector claim args = %d, want 3", len(args))
		}
		return db.claimProjectorWork(args[0].(time.Time), args[1].(string), args[2].(time.Time))
	case strings.Contains(query, "stage = 'reducer'"):
		if len(args) != 4 {
			return nil, fmt.Errorf("reducer claim args = %d, want 4", len(args))
		}
		return db.claimReducerWork(args[0].(time.Time), args[2].(string), args[3].(time.Time))
	default:
		return nil, fmt.Errorf("unexpected query: %s", query)
	}
}

func (db *proofDomainDB) updateWorkItemStatus(stage string, scopeID string, generationID string, leaseOwner string, status string) (sql.Result, error) {
	for key, item := range db.state.workItems {
		if item.stage == stage && item.scopeID == scopeID && item.generationID == generationID && item.leaseOwner == leaseOwner {
			item.status = status
			item.updatedAt = db.now
			item.leaseOwner = ""
			item.claimUntil = time.Time{}
			db.state.workItems[key] = item
			return proofResult{}, nil
		}
	}
	return nil, fmt.Errorf("work item not found for stage=%s scope=%s generation=%s", stage, scopeID, generationID)
}

func (db *proofDomainDB) updateWorkItemStatusByID(workItemID string, leaseOwner string, status string) (sql.Result, error) {
	item, ok := db.state.workItems[workItemID]
	if !ok {
		return nil, fmt.Errorf("work item %q not found", workItemID)
	}
	if item.leaseOwner != leaseOwner {
		return nil, fmt.Errorf("work item %q lease owner = %q, want %q", workItemID, item.leaseOwner, leaseOwner)
	}
	item.status = status
	item.updatedAt = db.now
	item.leaseOwner = ""
	item.claimUntil = time.Time{}
	db.state.workItems[workItemID] = item
	if status == "succeeded" {
		db.reducerAcked++
	}
	return proofResult{}, nil
}

func (db *proofDomainDB) claimProjectorWork(now time.Time, leaseOwner string, claimUntil time.Time) (Rows, error) {
	for key, item := range db.state.workItems {
		if item.stage != "projector" || item.status != "pending" {
			continue
		}
		if !item.visibleAt.IsZero() && item.visibleAt.After(now) {
			continue
		}
		item.status = "claimed"
		item.leaseOwner = leaseOwner
		item.claimUntil = claimUntil
		item.updatedAt = now
		db.state.workItems[key] = item

		scopeRow, ok := db.state.scopes[item.scopeID]
		if !ok {
			return nil, fmt.Errorf("scope %q not found", item.scopeID)
		}
		generationRow, ok := db.state.generations[item.generationID]
		if !ok {
			return nil, fmt.Errorf("generation %q not found", item.generationID)
		}

		return newProofRows([][]any{{
			scopeRow.ScopeID,
			scopeRow.SourceSystem,
			string(scopeRow.ScopeKind),
			scopeRow.ParentScopeID,
			string(scopeRow.CollectorKind),
			scopeRow.PartitionKey,
			generationRow.GenerationID,
			generationRow.ObservedAt,
			generationRow.IngestedAt,
			string(generationRow.Status),
			string(generationRow.TriggerKind),
			generationRow.FreshnessHint,
		}}), nil
	}

	return newProofRows(nil), nil
}

func (db *proofDomainDB) claimReducerWork(now time.Time, leaseOwner string, claimUntil time.Time) (Rows, error) {
	for key, item := range db.state.workItems {
		if item.stage != "reducer" || item.status != "pending" {
			continue
		}
		if !item.visibleAt.IsZero() && item.visibleAt.After(now) {
			continue
		}
		item.status = "claimed"
		item.leaseOwner = leaseOwner
		item.claimUntil = claimUntil
		item.updatedAt = now
		db.state.workItems[key] = item
		db.reducerClaims++
		return newProofRows([][]any{{
			item.workItemID,
			item.scopeID,
			item.generationID,
			item.domain,
			item.createdAt,
			item.visibleAt,
			item.payload,
		}}), nil
	}

	return newProofRows(nil), nil
}

func (tx *proofDomainTx) ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error) {
	_ = ctx
	switch {
	case strings.Contains(query, "INSERT INTO ingestion_scopes"):
		scopeValue := scope.IngestionScope{
			ScopeID:       args[0].(string),
			ScopeKind:     scope.ScopeKind(args[1].(string)),
			SourceSystem:  args[2].(string),
			ParentScopeID: stringFromAny(args[4]),
			CollectorKind: scope.CollectorKind(args[5].(string)),
			PartitionKey:  args[6].(string),
			Metadata:      nil,
		}
		tx.state.scopes[scopeValue.ScopeID] = scopeValue
		return proofResult{}, nil
	case strings.Contains(query, "INSERT INTO scope_generations"):
		generation := scope.ScopeGeneration{
			GenerationID:  args[0].(string),
			ScopeID:       args[1].(string),
			TriggerKind:   scope.TriggerKind(args[2].(string)),
			FreshnessHint: stringFromAny(args[3]),
			ObservedAt:    args[4].(time.Time).UTC(),
			IngestedAt:    args[5].(time.Time).UTC(),
			Status:        scope.GenerationStatus(args[6].(string)),
		}
		tx.state.generations[generation.GenerationID] = generation
		return proofResult{}, nil
	case strings.Contains(query, "INSERT INTO fact_records"):
		payload, err := unmarshalPayload(args[12].([]byte))
		if err != nil {
			return nil, err
		}
		envelope := facts.Envelope{
			FactID:        args[0].(string),
			ScopeID:       args[1].(string),
			GenerationID:  args[2].(string),
			FactKind:      args[3].(string),
			StableFactKey: args[4].(string),
			ObservedAt:    args[9].(time.Time).UTC(),
			IsTombstone:   args[11].(bool),
			Payload:       payload,
			SourceRef: facts.Ref{
				SourceSystem:   args[5].(string),
				ScopeID:        args[1].(string),
				GenerationID:   args[2].(string),
				FactKey:        args[6].(string),
				SourceURI:      stringFromAny(args[7]),
				SourceRecordID: stringFromAny(args[8]),
			},
		}
		tx.state.facts[envelope.FactID] = envelope
		return proofResult{}, nil
	case strings.Contains(query, "INSERT INTO fact_work_items") && strings.Contains(query, "'projector'"):
		workItem := proofWorkItem{
			workItemID:   args[0].(string),
			stage:        "projector",
			domain:       args[3].(string),
			status:       "pending",
			scopeID:      args[1].(string),
			generationID: args[2].(string),
			visibleAt:    args[4].(time.Time).UTC(),
			createdAt:    args[4].(time.Time).UTC(),
			updatedAt:    args[4].(time.Time).UTC(),
		}
		tx.state.workItems[workItem.workItemID] = workItem
		return proofResult{}, nil
	default:
		return nil, fmt.Errorf("unexpected tx exec query: %s", query)
	}
}

func (tx *proofDomainTx) QueryContext(context.Context, string, ...any) (Rows, error) {
	return nil, errors.New("unexpected query in transaction")
}

func (tx *proofDomainTx) Commit() error {
	tx.db.state = tx.state
	return nil
}

func (tx *proofDomainTx) Rollback() error { return nil }

type proofDomainTx struct {
	db    *proofDomainDB
	state proofState
}

type proofRows struct {
	rows  [][]any
	index int
}

func newProofRows(rows [][]any) *proofRows {
	return &proofRows{rows: rows}
}

func (r *proofRows) Next() bool {
	return r.index < len(r.rows)
}

func (r *proofRows) Scan(dest ...any) error {
	if r.index >= len(r.rows) {
		return errors.New("scan called without row")
	}
	row := r.rows[r.index]
	if len(dest) != len(row) {
		return fmt.Errorf("scan destination count = %d, want %d", len(dest), len(row))
	}

	for i := range dest {
		switch target := dest[i].(type) {
		case *string:
			value, ok := row[i].(string)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want string", i, row[i])
			}
			*target = value
		case *bool:
			value, ok := row[i].(bool)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want bool", i, row[i])
			}
			*target = value
		case *[]byte:
			value, ok := row[i].([]byte)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want []byte", i, row[i])
			}
			*target = value
		case *time.Time:
			value, ok := row[i].(time.Time)
			if !ok {
				return fmt.Errorf("row[%d] type = %T, want time.Time", i, row[i])
			}
			*target = value
		default:
			return fmt.Errorf("unsupported scan target %T", dest[i])
		}
	}

	r.index++
	return nil
}

func (r *proofRows) Err() error { return nil }

func (r *proofRows) Close() error { return nil }

type proofResult struct{}

func (proofResult) LastInsertId() (int64, error) { return 0, nil }
func (proofResult) RowsAffected() (int64, error) { return 1, nil }

func cloneScopes(input map[string]scope.IngestionScope) map[string]scope.IngestionScope {
	cloned := make(map[string]scope.IngestionScope, len(input))
	for key, value := range input {
		cloned[key] = value
	}
	return cloned
}

func cloneGenerations(input map[string]scope.ScopeGeneration) map[string]scope.ScopeGeneration {
	cloned := make(map[string]scope.ScopeGeneration, len(input))
	for key, value := range input {
		cloned[key] = value
	}
	return cloned
}

func cloneFacts(input map[string]facts.Envelope) map[string]facts.Envelope {
	cloned := make(map[string]facts.Envelope, len(input))
	for key, value := range input {
		cloned[key] = value.Clone()
	}
	return cloned
}

func cloneWorkItems(input map[string]proofWorkItem) map[string]proofWorkItem {
	cloned := make(map[string]proofWorkItem, len(input))
	for key, value := range input {
		cloned[key] = value
	}
	return cloned
}

func proofFactRows(input map[string]facts.Envelope, scopeID, generationID string) [][]any {
	rows := [][]any{}
	for _, envelope := range input {
		if envelope.ScopeID != scopeID || envelope.GenerationID != generationID {
			continue
		}
		payload, _ := json.Marshal(envelope.Payload)
		rows = append(rows, []any{
			envelope.FactID,
			envelope.ScopeID,
			envelope.GenerationID,
			envelope.FactKind,
			envelope.StableFactKey,
			envelope.SourceRef.SourceSystem,
			envelope.SourceRef.FactKey,
			envelope.SourceRef.SourceURI,
			envelope.SourceRef.SourceRecordID,
			envelope.ObservedAt.UTC(),
			envelope.IsTombstone,
			payload,
		})
	}
	return rows
}

func stringFromAny(value any) string {
	text, _ := value.(string)
	return text
}

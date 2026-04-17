package postgres

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

// CodeCallIntentWriter atomically persists code-call shared intents and their
// authoritative bounded-unit acceptance rows when the underlying database
// supports transactions.
type CodeCallIntentWriter struct {
	db       ExecQueryer
	beginner Beginner
}

// NewCodeCallIntentWriter creates a code-call writer backed by the provided
// database handle.
func NewCodeCallIntentWriter(db ExecQueryer) *CodeCallIntentWriter {
	writer := &CodeCallIntentWriter{db: db}
	if beginner, ok := db.(Beginner); ok {
		writer.beginner = beginner
	}
	return writer
}

// UpsertIntents persists code-call intents and acceptance rows together.
func (w *CodeCallIntentWriter) UpsertIntents(ctx context.Context, rows []reducer.SharedProjectionIntentRow) error {
	if len(rows) == 0 {
		return nil
	}

	acceptanceRows, err := buildAcceptanceRows(rows)
	if err != nil {
		return err
	}

	if w.beginner == nil {
		return upsertCodeCallArtifacts(ctx, w.db, rows, acceptanceRows)
	}

	tx, err := w.beginner.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin code call intent transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if err := upsertCodeCallArtifacts(ctx, tx, rows, acceptanceRows); err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit code call intent transaction: %w", err)
	}
	return nil
}

func upsertCodeCallArtifacts(
	ctx context.Context,
	db ExecQueryer,
	intentRows []reducer.SharedProjectionIntentRow,
	acceptanceRows []SharedProjectionAcceptance,
) error {
	if err := NewSharedIntentStore(db).UpsertIntents(ctx, intentRows); err != nil {
		return fmt.Errorf("upsert shared intents: %w", err)
	}
	if err := NewSharedProjectionAcceptanceStore(db).Upsert(ctx, acceptanceRows); err != nil {
		return fmt.Errorf("upsert shared projection acceptance: %w", err)
	}
	return nil
}

func buildAcceptanceRows(rows []reducer.SharedProjectionIntentRow) ([]SharedProjectionAcceptance, error) {
	byKey := make(map[reducer.SharedProjectionAcceptanceKey]SharedProjectionAcceptance, len(rows))

	for _, row := range rows {
		key, ok := row.AcceptanceKey()
		if !ok {
			return nil, fmt.Errorf("code call intent %q is missing acceptance identity", row.IntentID)
		}
		generationID := strings.TrimSpace(row.GenerationID)
		if generationID == "" {
			return nil, fmt.Errorf("code call intent %q is missing generation_id", row.IntentID)
		}

		acceptedAt := row.CreatedAt.UTC()
		if acceptedAt.IsZero() {
			acceptedAt = time.Now().UTC()
		}

		current, exists := byKey[key]
		if exists {
			if current.GenerationID != generationID {
				return nil, fmt.Errorf(
					"acceptance key %q/%q/%q has mixed generations %q and %q",
					key.ScopeID,
					key.AcceptanceUnitID,
					key.SourceRunID,
					current.GenerationID,
					generationID,
				)
			}
			if acceptedAt.After(current.UpdatedAt) {
				current.AcceptedAt = acceptedAt
				current.UpdatedAt = acceptedAt
				byKey[key] = current
			}
			continue
		}

		byKey[key] = SharedProjectionAcceptance{
			ScopeID:          key.ScopeID,
			AcceptanceUnitID: key.AcceptanceUnitID,
			SourceRunID:      key.SourceRunID,
			GenerationID:     generationID,
			AcceptedAt:       acceptedAt,
			UpdatedAt:        acceptedAt,
		}
	}

	acceptanceRows := make([]SharedProjectionAcceptance, 0, len(byKey))
	for _, row := range byKey {
		acceptanceRows = append(acceptanceRows, row)
	}
	return acceptanceRows, nil
}

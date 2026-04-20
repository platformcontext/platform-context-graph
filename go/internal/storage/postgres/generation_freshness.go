package postgres

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

const isCurrentGenerationSQL = `
SELECT active_generation_id
FROM ingestion_scopes
WHERE scope_id = $1
`

// NewGenerationFreshnessCheck returns a GenerationFreshnessCheck backed by
// the ingestion_scopes.active_generation_id denormalized column.
func NewGenerationFreshnessCheck(db ExecQueryer) reducer.GenerationFreshnessCheck {
	return func(ctx context.Context, scopeID, generationID string) (bool, error) {
		rows, err := db.QueryContext(ctx, isCurrentGenerationSQL, scopeID)
		if err != nil {
			return false, fmt.Errorf("query active generation for scope %s: %w", scopeID, err)
		}
		defer func() { _ = rows.Close() }()

		if !rows.Next() {
			// Unknown scope — assume current (defensive, let handler decide).
			return true, nil
		}

		var activeGenID sql.NullString
		if err := rows.Scan(&activeGenID); err != nil {
			return false, fmt.Errorf("scan active generation for scope %s: %w", scopeID, err)
		}

		if !activeGenID.Valid {
			// No active generation yet — assume current.
			return true, nil
		}

		return activeGenID.String == generationID, nil
	}
}

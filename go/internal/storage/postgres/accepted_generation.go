package postgres

import (
	"context"
	"database/sql"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

const acceptedGenerationLookupSQL = `
SELECT accepted_generation_id
FROM fact_work_items
WHERE repository_id = $1
  AND source_run_id = $2
  AND shared_projection_pending = TRUE
  AND accepted_generation_id IS NOT NULL
ORDER BY updated_at DESC, work_item_id DESC
LIMIT 1
`

// NewAcceptedGenerationLookup creates an AcceptedGenerationLookup backed by
// PostgreSQL fact_work_items queries. Returns the accepted_generation_id for a
// given (repository_id, source_run_id) pair when shared projection is pending.
// Returns empty string and false when no matching row exists.
func NewAcceptedGenerationLookup(db ExecQueryer) reducer.AcceptedGenerationLookup {
	return func(repositoryID, sourceRunID string) (string, bool) {
		ctx := context.Background()
		rows, err := db.QueryContext(ctx, acceptedGenerationLookupSQL, repositoryID, sourceRunID)
		if err != nil {
			return "", false
		}
		defer func() { _ = rows.Close() }()

		if !rows.Next() {
			return "", false
		}

		var acceptedGenerationID string
		if err := rows.Scan(&acceptedGenerationID); err != nil {
			if err == sql.ErrNoRows {
				return "", false
			}
			return "", false
		}

		return acceptedGenerationID, true
	}
}

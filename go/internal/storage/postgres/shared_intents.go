package postgres

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

const sharedIntentSchemaSQL = `
CREATE TABLE IF NOT EXISTS shared_projection_intents (
    intent_id TEXT PRIMARY KEY,
    projection_domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS shared_projection_intents_repo_run_idx
    ON shared_projection_intents (repository_id, source_run_id, projection_domain, created_at);
CREATE INDEX IF NOT EXISTS shared_projection_intents_pending_idx
    ON shared_projection_intents (projection_domain, completed_at, created_at);

CREATE TABLE IF NOT EXISTS shared_projection_partition_leases (
    projection_domain TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    partition_count INTEGER NOT NULL,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (projection_domain, partition_id, partition_count)
);
`

// SharedIntentSchemaSQL returns the DDL for shared projection intent tables.
func SharedIntentSchemaSQL() string {
	return sharedIntentSchemaSQL
}

const upsertSharedIntentSQL = `
INSERT INTO shared_projection_intents (
    intent_id, projection_domain, partition_key, repository_id,
    source_run_id, generation_id, payload, created_at, completed_at
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (intent_id) DO UPDATE
SET projection_domain = EXCLUDED.projection_domain,
    partition_key = EXCLUDED.partition_key,
    repository_id = EXCLUDED.repository_id,
    source_run_id = EXCLUDED.source_run_id,
    generation_id = EXCLUDED.generation_id,
    payload = EXCLUDED.payload,
    created_at = EXCLUDED.created_at,
    completed_at = COALESCE(
        shared_projection_intents.completed_at,
        EXCLUDED.completed_at
    )
`

const listSharedIntentsSQL = `
SELECT intent_id, projection_domain, partition_key, repository_id,
       source_run_id, generation_id, payload, created_at, completed_at
FROM shared_projection_intents
WHERE repository_id = $1
  AND source_run_id = $2
  AND ($3 = '' OR projection_domain = $3)
ORDER BY created_at ASC, intent_id ASC
LIMIT $4
`

const listPendingDomainIntentsSQL = `
SELECT intent_id, projection_domain, partition_key, repository_id,
       source_run_id, generation_id, payload, created_at, completed_at
FROM shared_projection_intents
WHERE projection_domain = $1
  AND completed_at IS NULL
ORDER BY created_at ASC, intent_id ASC
LIMIT $2
`

const markIntentsCompletedSQL = `
UPDATE shared_projection_intents
SET completed_at = $1
WHERE intent_id = $2
`

const listPendingRepoRunIntentsSQL = `
SELECT intent_id, projection_domain, partition_key, repository_id,
       source_run_id, generation_id, payload, created_at, completed_at
FROM shared_projection_intents
WHERE repository_id = $1
  AND source_run_id = $2
  AND projection_domain = $3
  AND completed_at IS NULL
ORDER BY created_at ASC, intent_id ASC
LIMIT $4
`

const countPendingGenerationIntentsSQL = `
SELECT COUNT(*) AS pending_count
FROM shared_projection_intents
WHERE repository_id = $1
  AND source_run_id = $2
  AND generation_id = $3
  AND projection_domain = $4
  AND completed_at IS NULL
`

const claimPartitionLeaseSQL = `
INSERT INTO shared_projection_partition_leases (
    projection_domain, partition_id, partition_count,
    lease_owner, lease_expires_at, updated_at
) VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (projection_domain, partition_id, partition_count) DO UPDATE
SET lease_owner = EXCLUDED.lease_owner,
    lease_expires_at = EXCLUDED.lease_expires_at,
    updated_at = EXCLUDED.updated_at
WHERE shared_projection_partition_leases.lease_expires_at IS NULL
   OR shared_projection_partition_leases.lease_expires_at <= $6
   OR shared_projection_partition_leases.lease_owner = $4
RETURNING projection_domain
`

const releasePartitionLeaseSQL = `
UPDATE shared_projection_partition_leases
SET lease_owner = NULL,
    lease_expires_at = NULL,
    updated_at = $5
WHERE projection_domain = $1
  AND partition_id = $2
  AND partition_count = $3
  AND lease_owner = $4
`

// SharedIntentFilter specifies query parameters for listing shared intents.
type SharedIntentFilter struct {
	RepositoryID     string
	SourceRunID      string
	ProjectionDomain *string
	Limit            int
}

// SharedIntentStore persists shared projection intents in PostgreSQL.
type SharedIntentStore struct {
	db ExecQueryer
}

// NewSharedIntentStore creates a shared intent store backed by the given
// database.
func NewSharedIntentStore(db ExecQueryer) *SharedIntentStore {
	return &SharedIntentStore{db: db}
}

// EnsureSchema applies the shared projection intent DDL.
func (s *SharedIntentStore) EnsureSchema(ctx context.Context) error {
	_, err := s.db.ExecContext(ctx, sharedIntentSchemaSQL)
	return err
}

// UpsertIntents inserts or updates shared projection intents.
func (s *SharedIntentStore) UpsertIntents(ctx context.Context, rows []reducer.SharedProjectionIntentRow) error {
	if len(rows) == 0 {
		return nil
	}

	for _, r := range rows {
		payloadBytes, err := json.Marshal(r.Payload)
		if err != nil {
			return fmt.Errorf("marshal payload: %w", err)
		}

		var completedAt any
		if r.CompletedAt != nil {
			completedAt = *r.CompletedAt
		}

		_, err = s.db.ExecContext(ctx, upsertSharedIntentSQL,
			r.IntentID,
			r.ProjectionDomain,
			r.PartitionKey,
			r.RepositoryID,
			r.SourceRunID,
			r.GenerationID,
			payloadBytes,
			r.CreatedAt,
			completedAt,
		)
		if err != nil {
			return err
		}
	}

	return nil
}

// ListIntents returns persisted intents for one repository/run pair.
func (s *SharedIntentStore) ListIntents(ctx context.Context, f SharedIntentFilter) ([]reducer.SharedProjectionIntentRow, error) {
	limit := max(f.Limit, 1)

	projDomain := ""
	if f.ProjectionDomain != nil {
		projDomain = *f.ProjectionDomain
	}

	sqlRows, err := s.db.QueryContext(ctx, listSharedIntentsSQL,
		f.RepositoryID,
		f.SourceRunID,
		projDomain,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer sqlRows.Close()

	return scanSharedIntentRows(sqlRows)
}

// ListPendingDomainIntents returns uncompleted intents for one projection
// domain.
func (s *SharedIntentStore) ListPendingDomainIntents(ctx context.Context, domain string, limit int) ([]reducer.SharedProjectionIntentRow, error) {
	l := max(limit, 1)

	sqlRows, err := s.db.QueryContext(ctx, listPendingDomainIntentsSQL, domain, l)
	if err != nil {
		return nil, err
	}
	defer sqlRows.Close()

	return scanSharedIntentRows(sqlRows)
}

// MarkIntentsCompleted marks intents as completed by setting completed_at.
func (s *SharedIntentStore) MarkIntentsCompleted(ctx context.Context, intentIDs []string, completedAt time.Time) error {
	if len(intentIDs) == 0 {
		return nil
	}

	for _, id := range intentIDs {
		_, err := s.db.ExecContext(ctx, markIntentsCompletedSQL, completedAt, id)
		if err != nil {
			return err
		}
	}

	return nil
}

// ClaimPartitionLease attempts to claim a partition lease. Returns true if the
// lease was successfully claimed, false if it is held by another worker.
func (s *SharedIntentStore) ClaimPartitionLease(ctx context.Context, domain string, partitionID, partitionCount int, leaseOwner string, leaseTTL time.Duration) (bool, error) {
	now := time.Now().UTC()
	leaseExpiresAt := now.Add(leaseTTL)

	rows, err := s.db.QueryContext(ctx, claimPartitionLeaseSQL,
		domain,
		partitionID,
		partitionCount,
		leaseOwner,
		leaseExpiresAt,
		now,
	)
	if err != nil {
		return false, fmt.Errorf("claim partition lease: %w", err)
	}
	defer rows.Close()

	if !rows.Next() {
		return false, nil
	}

	var projectionDomain string
	if err := rows.Scan(&projectionDomain); err != nil {
		return false, fmt.Errorf("scan lease claim result: %w", err)
	}

	return true, rows.Err()
}

// ReleasePartitionLease releases a partition lease owned by the given worker.
func (s *SharedIntentStore) ReleasePartitionLease(ctx context.Context, domain string, partitionID, partitionCount int, leaseOwner string) error {
	now := time.Now().UTC()

	_, err := s.db.ExecContext(ctx, releasePartitionLeaseSQL,
		domain,
		partitionID,
		partitionCount,
		leaseOwner,
		now,
	)
	if err != nil {
		return fmt.Errorf("release partition lease: %w", err)
	}

	return nil
}

// ListPendingRepoRunIntents lists uncompleted intents for a specific repository,
// source run, and projection domain.
func (s *SharedIntentStore) ListPendingRepoRunIntents(ctx context.Context, repositoryID, sourceRunID, domain string, limit int) ([]reducer.SharedProjectionIntentRow, error) {
	l := max(limit, 1)

	sqlRows, err := s.db.QueryContext(ctx, listPendingRepoRunIntentsSQL,
		repositoryID,
		sourceRunID,
		domain,
		l,
	)
	if err != nil {
		return nil, err
	}
	defer sqlRows.Close()

	return scanSharedIntentRows(sqlRows)
}

// CountPendingGenerationIntents counts uncompleted intents for a specific
// repository, source run, generation, and projection domain.
func (s *SharedIntentStore) CountPendingGenerationIntents(ctx context.Context, repositoryID, sourceRunID, generationID, domain string) (int, error) {
	rows, err := s.db.QueryContext(ctx, countPendingGenerationIntentsSQL,
		repositoryID,
		sourceRunID,
		generationID,
		domain,
	)
	if err != nil {
		return 0, fmt.Errorf("query pending generation intents: %w", err)
	}
	defer rows.Close()

	var count int
	if rows.Next() {
		if err := rows.Scan(&count); err != nil {
			return 0, fmt.Errorf("scan count: %w", err)
		}
	}

	return count, rows.Err()
}

func scanSharedIntentRows(rows Rows) ([]reducer.SharedProjectionIntentRow, error) {
	var result []reducer.SharedProjectionIntentRow
	for rows.Next() {
		var r reducer.SharedProjectionIntentRow
		var payloadBytes []byte
		var completedAt sql.NullTime
		if err := rows.Scan(
			&r.IntentID,
			&r.ProjectionDomain,
			&r.PartitionKey,
			&r.RepositoryID,
			&r.SourceRunID,
			&r.GenerationID,
			&payloadBytes,
			&r.CreatedAt,
			&completedAt,
		); err != nil {
			return nil, fmt.Errorf("scan shared intent: %w", err)
		}
		if len(payloadBytes) > 0 {
			if err := json.Unmarshal(payloadBytes, &r.Payload); err != nil {
				return nil, fmt.Errorf("unmarshal payload: %w", err)
			}
		}
		if completedAt.Valid {
			r.CompletedAt = &completedAt.Time
		}
		result = append(result, r)
	}

	return result, rows.Err()
}

// sharedIntentBootstrapDefinition returns the schema definition for the
// bootstrap registry.
func sharedIntentBootstrapDefinition() Definition {
	return Definition{
		Name: "shared_projection_intents",
		Path: "schema/data-plane/postgres/008_shared_projection_intents.sql",
		SQL:  sharedIntentSchemaSQL,
	}
}

// init registers the shared intent schema in the bootstrap definitions.
func init() {
	bootstrapDefinitions = append(bootstrapDefinitions, sharedIntentBootstrapDefinition())
}

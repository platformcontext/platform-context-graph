package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

const (
	scopeCountsQuery = `
SELECT status, COUNT(*) AS count
FROM ingestion_scopes
GROUP BY status
ORDER BY status
`
	generationCountsQuery = `
SELECT status, COUNT(*) AS count
FROM scope_generations
GROUP BY status
ORDER BY status
`
	stageCountsQuery = `
SELECT stage, status, COUNT(*) AS count
FROM fact_work_items
GROUP BY stage, status
ORDER BY stage, status
`
	domainBacklogQuery = `
SELECT domain,
       COUNT(*) FILTER (WHERE status IN ('pending', 'claimed', 'running', 'retrying')) AS outstanding_count,
       COUNT(*) FILTER (WHERE status = 'retrying') AS retrying_count,
       COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
       COALESCE(
         EXTRACT(
           EPOCH FROM (
             $1 - (
               MIN(created_at)
                 FILTER (WHERE status IN ('pending', 'claimed', 'running', 'retrying'))
             )
           )
         ),
         0
       ) AS oldest_outstanding_age_seconds
FROM fact_work_items
GROUP BY domain
HAVING COUNT(*) FILTER (WHERE status IN ('pending', 'claimed', 'running', 'retrying', 'failed')) > 0
ORDER BY outstanding_count DESC, oldest_outstanding_age_seconds DESC, domain ASC
`
	queueSnapshotQuery = `
SELECT COUNT(*) AS total_count,
       COUNT(*) FILTER (WHERE status IN ('pending', 'claimed', 'running', 'retrying')) AS outstanding_count,
       COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
       COUNT(*) FILTER (WHERE status IN ('claimed', 'running')) AS in_flight_count,
       COUNT(*) FILTER (WHERE status = 'retrying') AS retrying_count,
       COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded_count,
       COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
       COALESCE(
         EXTRACT(
           EPOCH FROM (
             $1 - (
               MIN(created_at)
                 FILTER (WHERE status IN ('pending', 'claimed', 'running', 'retrying'))
             )
           )
         ),
         0
       ) AS oldest_outstanding_age_seconds,
       COUNT(*) FILTER (
         WHERE status IN ('claimed', 'running')
           AND claim_until IS NOT NULL
           AND claim_until < $1
       ) AS overdue_claim_count
FROM fact_work_items
`
)

// Rows is the small read-only row cursor surface used by the status reader.
type Rows interface {
	Next() bool
	Scan(...any) error
	Err() error
	Close() error
}

// Queryer is the small read-only SQL adapter needed by the status reader.
type Queryer interface {
	QueryContext(context.Context, string, ...any) (Rows, error)
}

// SQLQueryer adapts a *sql.DB into the status query surface.
type SQLQueryer struct {
	DB *sql.DB
}

// QueryContext implements Queryer against a sql.DB.
func (q SQLQueryer) QueryContext(ctx context.Context, query string, args ...any) (Rows, error) {
	return q.DB.QueryContext(ctx, query, args...)
}

// StatusStore reads live operator status aggregates from the Wave 2 schema.
type StatusStore struct {
	queryer Queryer
}

// NewStatusStore constructs a read-only status store.
func NewStatusStore(queryer Queryer) StatusStore {
	return StatusStore{queryer: queryer}
}

// ReadRawSnapshot returns the raw aggregate snapshot needed by the operator
// status surface.
func (s StatusStore) ReadRawSnapshot(ctx context.Context, asOf time.Time) (statuspkg.RawSnapshot, error) {
	return s.ReadStatusSnapshot(ctx, asOf)
}

// ReadStatusSnapshot returns the raw aggregate snapshot needed by the shared
// operator status surface.
func (s StatusStore) ReadStatusSnapshot(ctx context.Context, asOf time.Time) (statuspkg.RawSnapshot, error) {
	if s.queryer == nil {
		return statuspkg.RawSnapshot{}, fmt.Errorf("queryer is required")
	}

	scopeCounts, err := listNamedCounts(ctx, s.queryer, scopeCountsQuery, "list scope counts")
	if err != nil {
		return statuspkg.RawSnapshot{}, err
	}
	generationCounts, err := listNamedCounts(ctx, s.queryer, generationCountsQuery, "list generation counts")
	if err != nil {
		return statuspkg.RawSnapshot{}, err
	}
	scopeActivity := scopeActivityFromCounts(scopeCounts, generationCounts)
	stageCounts, err := listStageCounts(ctx, s.queryer)
	if err != nil {
		return statuspkg.RawSnapshot{}, err
	}
	domainBacklogs, err := listDomainBacklogs(ctx, s.queryer, asOf.UTC())
	if err != nil {
		return statuspkg.RawSnapshot{}, err
	}
	queueSnapshot, err := readQueueSnapshot(ctx, s.queryer, asOf.UTC())
	if err != nil {
		return statuspkg.RawSnapshot{}, err
	}

	return statuspkg.RawSnapshot{
		AsOf:             asOf.UTC(),
		ScopeCounts:      scopeCounts,
		ScopeActivity:    scopeActivity,
		GenerationCounts: generationCounts,
		StageCounts:      stageCounts,
		DomainBacklogs:   domainBacklogs,
		Queue:            queueSnapshot,
	}, nil
}

func scopeActivityFromCounts(scopeCounts []statuspkg.NamedCount, generationCounts []statuspkg.NamedCount) statuspkg.ScopeActivitySnapshot {
	activeScopes := namedCount(scopeCounts, "active")
	pendingGenerations := namedCount(generationCounts, "pending")
	if pendingGenerations > activeScopes {
		pendingGenerations = activeScopes
	}

	return statuspkg.ScopeActivitySnapshot{
		Active:  activeScopes,
		Changed: pendingGenerations,
	}
}

func namedCount(rows []statuspkg.NamedCount, name string) int {
	total := 0
	for _, row := range rows {
		if row.Name == name {
			total += row.Count
		}
	}

	return total
}

func listNamedCounts(
	ctx context.Context,
	queryer Queryer,
	query string,
	op string,
) ([]statuspkg.NamedCount, error) {
	rows, err := queryer.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", op, err)
	}
	defer rows.Close()

	counts := []statuspkg.NamedCount{}
	for rows.Next() {
		var name string
		var count int64
		if scanErr := rows.Scan(&name, &count); scanErr != nil {
			return nil, fmt.Errorf("%s: %w", op, scanErr)
		}
		counts = append(counts, statuspkg.NamedCount{
			Name:  name,
			Count: int(count),
		})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("%s: %w", op, err)
	}

	return counts, nil
}

func listStageCounts(ctx context.Context, queryer Queryer) ([]statuspkg.StageStatusCount, error) {
	rows, err := queryer.QueryContext(ctx, stageCountsQuery)
	if err != nil {
		return nil, fmt.Errorf("list stage counts: %w", err)
	}
	defer rows.Close()

	counts := []statuspkg.StageStatusCount{}
	for rows.Next() {
		var stage string
		var state string
		var count int64
		if scanErr := rows.Scan(&stage, &state, &count); scanErr != nil {
			return nil, fmt.Errorf("list stage counts: %w", scanErr)
		}
		counts = append(counts, statuspkg.StageStatusCount{
			Stage:  stage,
			Status: state,
			Count:  int(count),
		})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list stage counts: %w", err)
	}

	return counts, nil
}

func listDomainBacklogs(
	ctx context.Context,
	queryer Queryer,
	asOf time.Time,
) ([]statuspkg.DomainBacklog, error) {
	rows, err := queryer.QueryContext(ctx, domainBacklogQuery, asOf)
	if err != nil {
		return nil, fmt.Errorf("list domain backlogs: %w", err)
	}
	defer rows.Close()

	backlogs := []statuspkg.DomainBacklog{}
	for rows.Next() {
		var domain string
		var outstandingCount int64
		var retryingCount int64
		var failedCount int64
		var oldestOutstandingAgeSeconds float64
		if scanErr := rows.Scan(
			&domain,
			&outstandingCount,
			&retryingCount,
			&failedCount,
			&oldestOutstandingAgeSeconds,
		); scanErr != nil {
			return nil, fmt.Errorf("list domain backlogs: %w", scanErr)
		}
		backlogs = append(backlogs, statuspkg.DomainBacklog{
			Domain:      domain,
			Outstanding: int(outstandingCount),
			Retrying:    int(retryingCount),
			Failed:      int(failedCount),
			OldestAge:   durationFromSeconds(oldestOutstandingAgeSeconds),
		})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list domain backlogs: %w", err)
	}

	return backlogs, nil
}

func readQueueSnapshot(
	ctx context.Context,
	queryer Queryer,
	asOf time.Time,
) (statuspkg.QueueSnapshot, error) {
	rows, err := queryer.QueryContext(ctx, queueSnapshotQuery, asOf)
	if err != nil {
		return statuspkg.QueueSnapshot{}, fmt.Errorf("read queue snapshot: %w", err)
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return statuspkg.QueueSnapshot{}, fmt.Errorf("read queue snapshot: %w", err)
		}
		return statuspkg.QueueSnapshot{}, nil
	}

	var totalCount int64
	var outstandingCount int64
	var pendingCount int64
	var inFlightCount int64
	var retryingCount int64
	var succeededCount int64
	var failedCount int64
	var oldestOutstandingAgeSeconds float64
	var overdueClaimCount int64
	if scanErr := rows.Scan(
		&totalCount,
		&outstandingCount,
		&pendingCount,
		&inFlightCount,
		&retryingCount,
		&succeededCount,
		&failedCount,
		&oldestOutstandingAgeSeconds,
		&overdueClaimCount,
	); scanErr != nil {
		return statuspkg.QueueSnapshot{}, fmt.Errorf("read queue snapshot: %w", scanErr)
	}
	if err := rows.Err(); err != nil {
		return statuspkg.QueueSnapshot{}, fmt.Errorf("read queue snapshot: %w", err)
	}

	return statuspkg.QueueSnapshot{
		Total:                int(totalCount),
		Outstanding:          int(outstandingCount),
		Pending:              int(pendingCount),
		InFlight:             int(inFlightCount),
		Retrying:             int(retryingCount),
		Succeeded:            int(succeededCount),
		Failed:               int(failedCount),
		OldestOutstandingAge: durationFromSeconds(oldestOutstandingAgeSeconds),
		OverdueClaims:        int(overdueClaimCount),
	}, nil
}

func durationFromSeconds(value float64) time.Duration {
	return time.Duration(value * float64(time.Second))
}

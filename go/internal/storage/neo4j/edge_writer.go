package neo4j

import (
	"context"
	"fmt"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

// EdgeWriter implements reducer.SharedProjectionEdgeWriter by dispatching
// domain-specific canonical Cypher statements through a Neo4j Executor.
type EdgeWriter struct {
	executor Executor
}

// NewEdgeWriter returns an EdgeWriter backed by the given Executor.
func NewEdgeWriter(executor Executor) *EdgeWriter {
	return &EdgeWriter{executor: executor}
}

// WriteEdges writes canonical domain edges for the given rows. Each row is
// converted to a canonical upsert statement and executed individually.
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

	for i, row := range rows {
		stmt, err := buildWriteStatement(domain, row, evidenceSource)
		if err != nil {
			return fmt.Errorf("build write statement %d: %w", i, err)
		}
		if err := w.executor.Execute(ctx, stmt); err != nil {
			return fmt.Errorf("execute write statement %d: %w", i, err)
		}
	}

	return nil
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

func buildWriteStatement(
	domain string,
	row reducer.SharedProjectionIntentRow,
	evidenceSource string,
) (Statement, error) {
	switch domain {
	case reducer.DomainPlatformInfra:
		return BuildCanonicalInfrastructurePlatformUpsert(
			CanonicalInfrastructurePlatformParams{
				RepoID:              payloadString(row.Payload, "repo_id"),
				PlatformID:          payloadString(row.Payload, "platform_id"),
				PlatformName:        payloadString(row.Payload, "platform_name"),
				PlatformKind:        payloadString(row.Payload, "platform_kind"),
				PlatformProvider:    payloadString(row.Payload, "platform_provider"),
				PlatformEnvironment: payloadString(row.Payload, "platform_environment"),
				PlatformRegion:      payloadString(row.Payload, "platform_region"),
				PlatformLocator:     payloadString(row.Payload, "platform_locator"),
			},
			evidenceSource,
		), nil

	case reducer.DomainRepoDependency:
		return BuildCanonicalRepoDependencyUpsert(
			CanonicalRepoDependencyParams{
				RepoID:       payloadString(row.Payload, "repo_id"),
				TargetRepoID: payloadString(row.Payload, "target_repo_id"),
			},
			evidenceSource,
		), nil

	case reducer.DomainWorkloadDependency:
		return BuildCanonicalWorkloadDependencyUpsert(
			CanonicalWorkloadDependencyParams{
				WorkloadID:       payloadString(row.Payload, "workload_id"),
				TargetWorkloadID: payloadString(row.Payload, "target_workload_id"),
			},
			evidenceSource,
		), nil

	default:
		return Statement{}, fmt.Errorf("unsupported domain for write: %q", domain)
	}
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

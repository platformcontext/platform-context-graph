package collector

import (
	"context"
	"fmt"
	"log/slog"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/repositoryidentity"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

// RepositorySelector selects the repositories for one collector cycle.
type RepositorySelector interface {
	SelectRepositories(context.Context) (SelectionBatch, error)
}

// RepositorySnapshotter collects one narrowed parser/snapshot payload for one
// selected repository.
type RepositorySnapshotter interface {
	SnapshotRepository(context.Context, SelectedRepository) (RepositorySnapshot, error)
}

// SelectionBatch is one narrowed repository-selection batch for Go-owned fact
// shaping.
type SelectionBatch struct {
	ObservedAt   time.Time
	Repositories []SelectedRepository
}

// SelectedRepository is one repository chosen for the current collector cycle.
type SelectedRepository struct {
	RepoPath     string   `json:"repo_path"`
	RemoteURL    string   `json:"remote_url"`
	IsDependency bool     `json:"is_dependency"`
	DisplayName  string   `json:"display_name"`
	Language     string   `json:"language"`
	FileTargets  []string `json:"file_targets"`
}

// RepositorySnapshot captures one repository parse snapshot and content transport.
type RepositorySnapshot struct {
	RepoPath        string                  `json:"repo_path"`
	RemoteURL       string                  `json:"remote_url"`
	FileCount       int                     `json:"file_count"`
	ImportsMap      map[string][]string     `json:"imports_map"`
	FileData        []map[string]any        `json:"file_data"`
	ContentFiles    []ContentFileSnapshot   `json:"content_files"`
	ContentEntities []ContentEntitySnapshot `json:"content_entities"`
}

// ContentFileSnapshot captures one portable file-content record.
type ContentFileSnapshot struct {
	RelativePath    string `json:"relative_path"`
	Body            string `json:"content_body"`
	Digest          string `json:"content_digest"`
	Language        string `json:"language"`
	ArtifactType    string `json:"artifact_type"`
	TemplateDialect string `json:"template_dialect"`
	IACRelevant     *bool  `json:"iac_relevant"`
	CommitSHA       string `json:"commit_sha"`
}

// ContentEntitySnapshot captures one portable content-entity record.
type ContentEntitySnapshot struct {
	EntityID        string         `json:"entity_id"`
	RelativePath    string         `json:"relative_path"`
	EntityType      string         `json:"entity_type"`
	EntityName      string         `json:"entity_name"`
	StartLine       int            `json:"start_line"`
	EndLine         int            `json:"end_line"`
	StartByte       *int           `json:"start_byte"`
	EndByte         *int           `json:"end_byte"`
	Language        string         `json:"language"`
	ArtifactType    string         `json:"artifact_type"`
	TemplateDialect string         `json:"template_dialect"`
	IACRelevant     *bool          `json:"iac_relevant"`
	SourceCache     string         `json:"source_cache"`
	Metadata        map[string]any `json:"metadata"`
	IndexedAt       time.Time      `json:"indexed_at"`
}

// GitSource converts narrowed snapshot batches into durable collector generations.
type GitSource struct {
	Component       string
	Selector        RepositorySelector
	Snapshotter     RepositorySnapshotter
	Tracer          trace.Tracer
	Instruments     *telemetry.Instruments
	Logger          *slog.Logger
	SnapshotWorkers int
	pending         []CollectedGeneration
}

// Next returns one Go-shaped collected generation, collecting a new selection
// batch when needed.
func (s *GitSource) Next(ctx context.Context) (CollectedGeneration, bool, error) {
	if len(s.pending) == 0 {
		if s.Selector == nil {
			return CollectedGeneration{}, false, fmt.Errorf("git repository selector is required")
		}

		// Trace and measure scope assignment (discovery phase)
		var batch SelectionBatch
		var err error
		if s.Tracer != nil {
			ctx, span := s.Tracer.Start(ctx, telemetry.SpanScopeAssign)
			defer span.End()

			start := time.Now()
			batch, err = s.Selector.SelectRepositories(ctx)
			duration := time.Since(start).Seconds()

			if s.Instruments != nil {
				s.Instruments.ScopeAssignDuration.Record(ctx, duration,
					metric.WithAttributes(
						telemetry.AttrCollectorKind("git"),
						telemetry.AttrSourceSystem("git"),
					),
				)
			}

			if s.Logger != nil && err == nil {
				s.Logger.InfoContext(ctx, "collector discovery completed",
					slog.String("collector_kind", "git"),
					slog.Int("repository_count", len(batch.Repositories)),
				)
			}
		} else {
			batch, err = s.Selector.SelectRepositories(ctx)
		}

		if err != nil {
			return CollectedGeneration{}, false, err
		}
		collected, err := s.buildCollected(ctx, batch)
		if err != nil {
			return CollectedGeneration{}, false, err
		}
		s.pending = append(s.pending, collected...)
	}
	if len(s.pending) == 0 {
		return CollectedGeneration{}, false, nil
	}

	item := s.pending[0]
	s.pending = s.pending[1:]
	return item, true, nil
}

func (s *GitSource) buildCollected(
	ctx context.Context,
	batch SelectionBatch,
) ([]CollectedGeneration, error) {
	if len(batch.Repositories) == 0 {
		return nil, nil
	}
	if batch.ObservedAt.IsZero() {
		return nil, fmt.Errorf("selection batch observed_at is required")
	}
	if s.Snapshotter == nil {
		return nil, fmt.Errorf("git repository snapshotter is required")
	}

	resolvedRepositories := make([]SelectedRepository, 0, len(batch.Repositories))
	selectedRepositoryPaths := make([]string, 0, len(batch.Repositories))
	for _, repository := range batch.Repositories {
		repoPath, err := filepath.Abs(repository.RepoPath)
		if err != nil {
			return nil, fmt.Errorf("resolve selected repo path %q: %w", repository.RepoPath, err)
		}
		resolvedRepositories = append(
			resolvedRepositories,
			SelectedRepository{
				RepoPath:     repoPath,
				RemoteURL:    repository.RemoteURL,
				IsDependency: repository.IsDependency,
				DisplayName:  repository.DisplayName,
				Language:     repository.Language,
				FileTargets:  append([]string(nil), repository.FileTargets...),
			},
		)
		selectedRepositoryPaths = append(selectedRepositoryPaths, repoPath)
	}
	sourceRunID := facts.StableID(
		"GitCollectorSnapshotRun",
		map[string]any{
			"component":             s.componentName(),
			"observed_at":           batch.ObservedAt.UTC().Format(time.RFC3339Nano),
			"selected_repositories": selectedRepositoryPaths,
		},
	)

	// Sequential path when workers <= 1
	if s.SnapshotWorkers <= 1 {
		collected := make([]CollectedGeneration, 0, len(resolvedRepositories))
		for _, repository := range resolvedRepositories {
			generation, err := s.snapshotOneRepository(ctx, repository, sourceRunID, batch.ObservedAt.UTC(), 0)
			if err != nil {
				return nil, err
			}
			collected = append(collected, generation)
		}
		return collected, nil
	}

	// Concurrent path when workers > 1
	return s.buildCollectedConcurrent(ctx, resolvedRepositories, sourceRunID, batch.ObservedAt.UTC())
}

// snapshotOneRepository processes a single repository snapshot and returns a
// CollectedGeneration. This method records telemetry and handles all the
// snapshot-to-generation conversion logic.
func (s *GitSource) snapshotOneRepository(
	ctx context.Context,
	repository SelectedRepository,
	sourceRunID string,
	observedAt time.Time,
	workerID int,
) (CollectedGeneration, error) {
	var span trace.Span
	if s.Tracer != nil {
		ctx, span = s.Tracer.Start(ctx, telemetry.SpanFactEmit)
		defer span.End()
	}

	start := time.Now()
	snapshot, err := s.Snapshotter.SnapshotRepository(ctx, repository)
	if err != nil {
		return CollectedGeneration{}, fmt.Errorf("snapshot repository %q: %w", repository.RepoPath, err)
	}

	repoPath := repository.RepoPath
	if snapshot.RepoPath == "" {
		snapshot.RepoPath = repoPath
	}
	if snapshot.RemoteURL == "" {
		snapshot.RemoteURL = repository.RemoteURL
	}

	repositoryName := repository.DisplayName
	if strings.TrimSpace(repositoryName) == "" {
		repositoryName = filepath.Base(repoPath)
	}

	metadata, err := repositoryidentity.MetadataFor(
		repositoryName,
		repoPath,
		repository.RemoteURL,
	)
	if err != nil {
		return CollectedGeneration{}, fmt.Errorf("build repository metadata for %q: %w", repoPath, err)
	}

	generation := buildCollectedGeneration(
		repoPath,
		metadata,
		sourceRunID,
		observedAt,
		snapshot,
		repository.IsDependency,
	)

	duration := time.Since(start).Seconds()
	scopeID := generation.Scope.ScopeID

	// Record metrics
	if s.Instruments != nil {
		s.Instruments.RepoSnapshotDuration.Record(ctx, duration,
			metric.WithAttributes(telemetry.AttrScopeID(scopeID)),
		)
		s.Instruments.ReposSnapshotted.Add(ctx, 1,
			metric.WithAttributes(attribute.String("status", "succeeded")),
		)
		s.Instruments.FactEmitDuration.Record(ctx, duration,
			metric.WithAttributes(
				telemetry.AttrCollectorKind("git"),
				telemetry.AttrSourceSystem("git"),
				telemetry.AttrScopeID(scopeID),
			),
		)
		s.Instruments.FactsEmitted.Add(ctx, int64(len(generation.Facts)),
			metric.WithAttributes(
				telemetry.AttrCollectorKind("git"),
				telemetry.AttrSourceSystem("git"),
				telemetry.AttrScopeID(scopeID),
			),
		)
	}

	// Log completion
	if s.Logger != nil {
		logAttrs := []any{
			slog.String("collector_kind", "git"),
			slog.String("repo_path", repoPath),
			slog.Int("file_count", snapshot.FileCount),
			slog.Int("fact_count", len(generation.Facts)),
		}
		if workerID > 0 {
			logAttrs = append(logAttrs, slog.Int("worker_id", workerID))
		}
		s.Logger.InfoContext(ctx, "collector snapshot completed", logAttrs...)
	}

	return generation, nil
}

// buildCollectedConcurrent uses a worker pool to snapshot repositories
// concurrently. Workers claim repositories from a channel, snapshot them,
// and collect results. On first error, the context is cancelled and all
// errors are collected.
func (s *GitSource) buildCollectedConcurrent(
	ctx context.Context,
	repositories []SelectedRepository,
	sourceRunID string,
	observedAt time.Time,
) ([]CollectedGeneration, error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	repoChan := make(chan SelectedRepository, len(repositories))
	for _, repo := range repositories {
		repoChan <- repo
	}
	close(repoChan)

	type result struct {
		generation CollectedGeneration
		err        error
		index      int
	}

	resultChan := make(chan result, len(repositories))
	var wg sync.WaitGroup
	var completed atomic.Int64

	for i := 0; i < s.SnapshotWorkers; i++ {
		workerID := i + 1
		wg.Add(1)
		go func() {
			defer wg.Done()
			for repo := range repoChan {
				if ctx.Err() != nil {
					return
				}

				generation, err := s.snapshotOneRepository(ctx, repo, sourceRunID, observedAt, workerID)
				completed.Add(1)

				if err != nil {
					if s.Instruments != nil {
						s.Instruments.ReposSnapshotted.Add(ctx, 1,
							metric.WithAttributes(attribute.String("status", "failed")),
						)
					}
					resultChan <- result{err: err}
					cancel()
					return
				}

				resultChan <- result{generation: generation}
			}
		}()
	}

	wg.Wait()
	close(resultChan)

	// Collect results
	collected := make([]CollectedGeneration, 0, len(repositories))
	var errs []error
	for res := range resultChan {
		if res.err != nil {
			errs = append(errs, res.err)
		} else {
			collected = append(collected, res.generation)
		}
	}

	if len(errs) > 0 {
		return nil, fmt.Errorf("snapshot failed: %w", errs[0])
	}

	return collected, nil
}

func (s *GitSource) componentName() string {
	if s.Component == "" {
		return "collector-git"
	}
	return s.Component
}

func buildScope(repo repositoryidentity.Metadata) scope.IngestionScope {
	metadata := map[string]string{
		"repo_id":    repo.ID,
		"repo_name":  repo.Name,
		"source_key": repo.ID,
	}
	if repo.RepoSlug != "" {
		metadata["repo_slug"] = repo.RepoSlug
	}
	if repo.RemoteURL != "" {
		metadata["remote_url"] = repo.RemoteURL
	}
	if repo.LocalPath != "" {
		metadata["local_path"] = repo.LocalPath
	}

	return scope.IngestionScope{
		ScopeID:       "git-repository-scope:" + repo.ID,
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  repo.ID,
		Metadata:      metadata,
	}
}

func buildGeneration(
	scopeID string,
	sourceRunID string,
	repoPath string,
	observedAt time.Time,
	freshnessHint string,
) scope.ScopeGeneration {
	return scope.ScopeGeneration{
		GenerationID: facts.StableID(
			"GitRepositorySnapshot",
			map[string]any{
				"repo_path":     repoPath,
				"source_run_id": sourceRunID,
			},
		),
		ScopeID:       scopeID,
		ObservedAt:    observedAt,
		IngestedAt:    observedAt,
		Status:        scope.GenerationStatusPending,
		TriggerKind:   scope.TriggerKindSnapshot,
		FreshnessHint: freshnessHint,
	}
}

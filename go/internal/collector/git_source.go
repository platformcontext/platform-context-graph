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

// GitSource converts narrowed snapshot batches into durable collector
// generations. Generations are streamed through a bounded channel so memory
// stays proportional to the channel buffer size, not the total number of
// repositories.
type GitSource struct {
	Component       string
	Selector        RepositorySelector
	Snapshotter     RepositorySnapshotter
	Tracer          trace.Tracer
	Instruments     *telemetry.Instruments
	Logger          *slog.Logger
	SnapshotWorkers int

	// Streaming state, lazily initialized on first Next call.
	// The channel carries one CollectedGeneration at a time; the coordinator
	// goroutine closes it when all workers finish or on first error.
	stream    chan CollectedGeneration
	streamErr error
	started   bool
}

// Next returns one Go-shaped collected generation, streaming from background
// snapshot workers. On the first call it launches background goroutines that
// discover repos, snapshot them concurrently, and feed results through a
// bounded channel. Subsequent calls read one generation at a time.
//
// When the current batch is fully consumed the stream resets so the next call
// triggers a fresh discovery cycle (used by the ingester poll loop).
func (s *GitSource) Next(ctx context.Context) (CollectedGeneration, bool, error) {
	if !s.started {
		if s.Selector == nil {
			return CollectedGeneration{}, false, fmt.Errorf("git repository selector is required")
		}
		if err := s.startStream(ctx); err != nil {
			return CollectedGeneration{}, false, err
		}
		s.started = true
	}

	select {
	case gen, ok := <-s.stream:
		if !ok {
			// Channel closed: stream exhausted. Reset for next discovery cycle.
			s.started = false
			if s.streamErr != nil {
				err := s.streamErr
				s.streamErr = nil
				return CollectedGeneration{}, false, err
			}
			return CollectedGeneration{}, false, nil
		}
		return gen, true, nil
	case <-ctx.Done():
		return CollectedGeneration{}, false, ctx.Err()
	}
}

// startStream performs synchronous repo discovery, then launches background
// snapshot workers that feed generations into s.stream. The channel buffer
// equals the worker count, providing natural backpressure: workers block on
// send when the consumer hasn't committed the previous generation yet.
//
// Telemetry:
//   - Parent span: collector.stream (covers entire stream lifecycle)
//   - Child spans: fact.emit (one per repository, from snapshotOneRepository)
//   - Metrics: RepoSnapshotDuration, ReposSnapshotted, FactEmitDuration, FactsEmitted
//   - Logging: stream start (repos discovered, workers), stream end (completed, failed, duration)
func (s *GitSource) startStream(ctx context.Context) error {
	// Phase 1: Discovery (synchronous, fast)
	batch, err := s.discoverRepositories(ctx)
	if err != nil {
		return err
	}
	if len(batch.Repositories) == 0 {
		if s.Logger != nil {
			s.Logger.InfoContext(ctx, "collector stream: no repositories discovered",
				slog.String("collector_kind", "git"),
				slog.String("component", s.componentName()),
				telemetry.PhaseAttr(telemetry.PhaseDiscovery),
			)
		}
		s.stream = make(chan CollectedGeneration)
		close(s.stream)
		return nil
	}

	// Phase 2: Resolve paths and compute stable source run ID
	resolved, sourceRunID, err := s.resolveRepositories(batch)
	if err != nil {
		return err
	}

	// Phase 3: Launch background snapshot workers
	workers := s.SnapshotWorkers
	if workers <= 0 {
		workers = 1
	}
	// Buffer of 1: only one completed generation waits while the consumer
	// commits the previous one. This bounds memory to at most
	// (1 buffer + workers in-flight + 1 consuming) generations instead of
	// (workers buffer + workers in-flight + 1 consuming).
	s.stream = make(chan CollectedGeneration, 1)
	s.streamErr = nil

	// Start the parent stream span — kept open until coordinator closes it
	var streamSpan trace.Span
	streamCtx := ctx
	if s.Tracer != nil {
		streamCtx, streamSpan = s.Tracer.Start(ctx, telemetry.SpanCollectorStream,
			trace.WithAttributes(
				attribute.String("component", s.componentName()),
				attribute.Int("repository_count", len(resolved)),
				attribute.Int("snapshot_workers", workers),
			),
		)
	}

	streamStart := time.Now()
	if s.Logger != nil {
		s.Logger.InfoContext(streamCtx, "collector stream started",
			slog.String("collector_kind", "git"),
			slog.String("component", s.componentName()),
			slog.Int("repository_count", len(resolved)),
			slog.Int("snapshot_workers", workers),
			telemetry.PhaseAttr(telemetry.PhaseEmission),
		)
	}

	workerCtx, cancel := context.WithCancel(streamCtx)
	repoChan := make(chan SelectedRepository, workers)
	observedAt := batch.ObservedAt.UTC()

	// Feed repos into work channel
	go func() {
		defer close(repoChan)
		for _, repo := range resolved {
			select {
			case repoChan <- repo:
			case <-workerCtx.Done():
				return
			}
		}
	}()

	// Snapshot workers: read repos, snapshot, send generations
	var wg sync.WaitGroup
	var errOnce sync.Once
	var firstErr error
	var completed atomic.Int64

	for i := 0; i < workers; i++ {
		workerID := i + 1
		wg.Add(1)
		go func() {
			defer wg.Done()
			for repo := range repoChan {
				if workerCtx.Err() != nil {
					return
				}

				gen, err := s.snapshotOneRepository(
					workerCtx, repo, sourceRunID, observedAt, workerID,
				)
				if err != nil {
					if s.Instruments != nil {
						s.Instruments.ReposSnapshotted.Add(ctx, 1,
							metric.WithAttributes(attribute.String("status", "failed")),
						)
					}
					errOnce.Do(func() {
						firstErr = err
						cancel()
					})
					return
				}

				completed.Add(1)

				select {
				case s.stream <- gen:
				case <-workerCtx.Done():
					return
				}
			}
		}()
	}

	// Coordinator: wait for all workers, record telemetry, close channel.
	// The channel close happens-before any receive that returns ok==false,
	// so s.streamErr is safely visible to Next() without additional sync.
	go func() {
		wg.Wait()
		cancel()
		s.streamErr = firstErr

		streamDuration := time.Since(streamStart).Seconds()
		completedCount := completed.Load()

		// Record stream-level metrics
		if s.Instruments != nil {
			s.Instruments.CollectorObserveDuration.Record(ctx, streamDuration,
				metric.WithAttributes(
					telemetry.AttrCollectorKind("git"),
					attribute.String("component", s.componentName()),
				),
			)
		}

		// Close stream span
		if streamSpan != nil {
			streamSpan.SetAttributes(
				attribute.Int64("repos_completed", completedCount),
				attribute.Int("repos_total", len(resolved)),
				attribute.Float64("duration_seconds", streamDuration),
			)
			if firstErr != nil {
				streamSpan.RecordError(firstErr)
			}
			streamSpan.End()
		}

		// Log stream completion
		if s.Logger != nil {
			logAttrs := []any{
				slog.String("collector_kind", "git"),
				slog.String("component", s.componentName()),
				slog.Int64("repos_completed", completedCount),
				slog.Int("repos_total", len(resolved)),
				slog.Int("snapshot_workers", workers),
				slog.Float64("duration_seconds", streamDuration),
				telemetry.PhaseAttr(telemetry.PhaseEmission),
			}
			if firstErr != nil {
				logAttrs = append(logAttrs,
					slog.String("error", firstErr.Error()),
					telemetry.FailureClassAttr("stream_snapshot_failure"),
				)
				s.Logger.ErrorContext(ctx, "collector stream failed", logAttrs...)
			} else {
				s.Logger.InfoContext(ctx, "collector stream completed", logAttrs...)
			}
		}

		close(s.stream)
	}()

	return nil
}

// discoverRepositories runs repo selection with telemetry instrumentation.
func (s *GitSource) discoverRepositories(ctx context.Context) (SelectionBatch, error) {
	if s.Tracer != nil {
		ctx, span := s.Tracer.Start(ctx, telemetry.SpanScopeAssign)
		defer span.End()

		start := time.Now()
		batch, err := s.Selector.SelectRepositories(ctx)
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

		return batch, err
	}

	return s.Selector.SelectRepositories(ctx)
}

// resolveRepositories converts selected repositories to absolute paths and
// computes the stable source run ID.
func (s *GitSource) resolveRepositories(batch SelectionBatch) ([]SelectedRepository, string, error) {
	resolved := make([]SelectedRepository, 0, len(batch.Repositories))
	paths := make([]string, 0, len(batch.Repositories))

	for _, repo := range batch.Repositories {
		absPath, err := filepath.Abs(repo.RepoPath)
		if err != nil {
			return nil, "", fmt.Errorf("resolve selected repo path %q: %w", repo.RepoPath, err)
		}
		resolved = append(resolved, SelectedRepository{
			RepoPath:     absPath,
			RemoteURL:    repo.RemoteURL,
			IsDependency: repo.IsDependency,
			DisplayName:  repo.DisplayName,
			Language:     repo.Language,
			FileTargets:  append([]string(nil), repo.FileTargets...),
		})
		paths = append(paths, absPath)
	}

	sourceRunID := facts.StableID(
		"GitCollectorSnapshotRun",
		map[string]any{
			"component":             s.componentName(),
			"observed_at":           batch.ObservedAt.UTC().Format(time.RFC3339Nano),
			"selected_repositories": paths,
		},
	)

	return resolved, sourceRunID, nil
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

	generation := buildStreamingGeneration(
		repoPath,
		metadata,
		sourceRunID,
		observedAt,
		snapshot,
		repository.IsDependency,
	)

	duration := time.Since(start).Seconds()
	scopeID := generation.Scope.ScopeID
	factCount := generation.FactCount

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
		s.Instruments.FactsEmitted.Add(ctx, int64(factCount),
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
			slog.Int("fact_count", factCount),
		}
		if workerID > 0 {
			logAttrs = append(logAttrs, slog.Int("worker_id", workerID))
		}
		s.Logger.InfoContext(ctx, "collector snapshot completed", logAttrs...)
	}

	return generation, nil
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

package collector

import (
	"context"
	"fmt"
	"path/filepath"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/repositoryidentity"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

// SnapshotRunner collects one narrowed parser/snapshot batch.
type SnapshotRunner interface {
	CollectSnapshots(context.Context) (SnapshotBatch, error)
}

// SnapshotBatch is one narrowed compatibility batch for Go-owned fact shaping.
type SnapshotBatch struct {
	ObservedAt   time.Time
	Repositories []RepositorySnapshot
}

// RepositorySnapshot captures one repository parse snapshot and content transport.
type RepositorySnapshot struct {
	RepoPath        string                  `json:"repo_path"`
	RemoteURL       string                  `json:"remote_url"`
	FileCount       int                     `json:"file_count"`
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
	EntityID        string    `json:"entity_id"`
	RelativePath    string    `json:"relative_path"`
	EntityType      string    `json:"entity_type"`
	EntityName      string    `json:"entity_name"`
	StartLine       int       `json:"start_line"`
	EndLine         int       `json:"end_line"`
	StartByte       *int      `json:"start_byte"`
	EndByte         *int      `json:"end_byte"`
	Language        string    `json:"language"`
	ArtifactType    string    `json:"artifact_type"`
	TemplateDialect string    `json:"template_dialect"`
	IACRelevant     *bool     `json:"iac_relevant"`
	SourceCache     string    `json:"source_cache"`
	IndexedAt       time.Time `json:"indexed_at"`
}

// GitSource converts narrowed snapshot batches into durable collector generations.
type GitSource struct {
	Component string
	Runner    SnapshotRunner
	pending   []CollectedGeneration
}

// Next returns one Go-shaped collected generation, collecting a new snapshot batch when needed.
func (s *GitSource) Next(ctx context.Context) (CollectedGeneration, bool, error) {
	if len(s.pending) == 0 {
		if s.Runner == nil {
			return CollectedGeneration{}, false, fmt.Errorf("git snapshot runner is required")
		}
		batch, err := s.Runner.CollectSnapshots(ctx)
		if err != nil {
			return CollectedGeneration{}, false, err
		}
		collected, err := s.buildCollected(batch)
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

func (s *GitSource) buildCollected(batch SnapshotBatch) ([]CollectedGeneration, error) {
	if len(batch.Repositories) == 0 {
		return nil, nil
	}
	if batch.ObservedAt.IsZero() {
		return nil, fmt.Errorf("snapshot batch observed_at is required")
	}

	selectedRepositories := make([]string, 0, len(batch.Repositories))
	for _, repository := range batch.Repositories {
		selectedRepositories = append(selectedRepositories, repository.RepoPath)
	}
	sourceRunID := facts.StableID(
		"GitCollectorSnapshotRun",
		map[string]any{
			"component":             s.componentName(),
			"observed_at":           batch.ObservedAt.UTC().Format(time.RFC3339Nano),
			"selected_repositories": selectedRepositories,
		},
	)

	collected := make([]CollectedGeneration, 0, len(batch.Repositories))
	for _, repository := range batch.Repositories {
		repoPath, err := filepath.Abs(repository.RepoPath)
		if err != nil {
			return nil, fmt.Errorf("resolve repo path %q: %w", repository.RepoPath, err)
		}
		metadata, err := repositoryidentity.MetadataFor(
			filepath.Base(repoPath),
			repoPath,
			repository.RemoteURL,
		)
		if err != nil {
			return nil, fmt.Errorf("build repository metadata for %q: %w", repoPath, err)
		}
		collected = append(
			collected,
			buildCollectedGeneration(
				repoPath,
				metadata,
				sourceRunID,
				batch.ObservedAt.UTC(),
				repository,
			),
		)
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

func buildGeneration(scopeID string, sourceRunID string, repoPath string, observedAt time.Time) scope.ScopeGeneration {
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
		FreshnessHint: "snapshot",
	}
}

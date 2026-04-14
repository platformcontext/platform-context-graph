package collector

import (
	"context"
	"errors"
	"sort"
	"sync"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestGitSourceNextBuildsCollectedGenerationFromSelectionAndPerRepoSnapshots(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	firstRepoPath := t.TempDir()
	secondRepoPath := t.TempDir()
	selector := &stubRepositorySelector{
		batches: []SelectionBatch{{
			ObservedAt: observedAt,
			Repositories: []SelectedRepository{
				{
					RepoPath:  firstRepoPath,
					RemoteURL: "https://github.com/example/service-one",
				},
				{
					RepoPath:  secondRepoPath,
					RemoteURL: "https://github.com/example/service-two",
				},
			},
		}},
	}
	snapshotter := &stubRepositorySnapshotter{
		snapshots: map[string]RepositorySnapshot{
			firstRepoPath: {
				RepoPath:  firstRepoPath,
				RemoteURL: "https://github.com/example/service",
				FileCount: 1,
				ImportsMap: map[string][]string{
					"Worker": {firstRepoPath + "/app.py"},
				},
				FileData: []map[string]any{{
					"path": firstRepoPath + "/app.py",
					"lang": "python",
					"functions": []any{
						map[string]any{
							"name":        "handler",
							"line_number": 1,
							"uid":         "content-entity:e_fn123456789",
						},
					},
				}},
				ContentFiles: []ContentFileSnapshot{{
					RelativePath: "app.py",
					Body:         "def handler():\n    return 1\n",
					Digest:       "digest-1",
					Language:     "python",
				}},
				ContentEntities: []ContentEntitySnapshot{{
					EntityID:     "content-entity:e_fn123456789",
					RelativePath: "app.py",
					EntityType:   "Function",
					EntityName:   "handler",
					StartLine:    1,
					EndLine:      2,
					Language:     "python",
					SourceCache:  "def handler():\n    return 1\n",
					IndexedAt:    observedAt,
					Metadata: map[string]any{
						"docstring":  "Handles requests.",
						"decorators": []string{"@cached"},
					},
				}},
			},
			secondRepoPath: {
				RepoPath:  secondRepoPath,
				RemoteURL: "https://github.com/example/service-two",
				FileCount: 0,
			},
		},
	}

	source := &GitSource{
		Component:   "collector-git",
		Selector:    selector,
		Snapshotter: snapshotter,
	}

	// Collect both generations — order is non-deterministic with concurrent workers.
	collected1, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next(1) error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next(1) ok = false, want true")
	}
	collected2, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next(2) error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next(2) ok = false, want true")
	}

	facts1 := drainFactChannel(collected1.Facts)
	facts2 := drainFactChannel(collected2.Facts)

	// Identify which result is the full repo (6 facts) vs empty repo (3 facts).
	var fullCollected CollectedGeneration
	var fullFacts []facts.Envelope
	var emptyFacts []facts.Envelope
	switch {
	case len(facts1) == 6 && len(facts2) == 3:
		fullCollected = collected1
		fullFacts = facts1
		emptyFacts = facts2
	case len(facts1) == 3 && len(facts2) == 6:
		fullCollected = collected2
		fullFacts = facts2
		emptyFacts = facts1
	default:
		t.Fatalf("unexpected fact counts: %d and %d, want 6 and 3", len(facts1), len(facts2))
	}

	// Validate common scope/generation fields on the full repo.
	if got, want := fullCollected.Scope.SourceSystem, "git"; got != want {
		t.Fatalf("Scope.SourceSystem = %q, want %q", got, want)
	}
	if got, want := string(fullCollected.Scope.ScopeKind), "repository"; got != want {
		t.Fatalf("Scope.ScopeKind = %q, want %q", got, want)
	}
	if got, want := string(fullCollected.Generation.TriggerKind), "snapshot"; got != want {
		t.Fatalf("Generation.TriggerKind = %q, want %q", got, want)
	}

	wantKinds := []string{
		"repository",
		"file",
		"content",
		"content_entity",
		"shared_followup",
		"shared_followup",
	}
	for i, want := range wantKinds {
		if got := fullFacts[i].FactKind; got != want {
			t.Fatalf("Facts[%d].FactKind = %q, want %q", i, got, want)
		}
	}

	repositoryFact := fullFacts[0]
	if _, ok := repositoryFact.Payload["source_run_id"].(string); !ok {
		t.Fatalf("repository fact source_run_id = %#v, want non-empty string", repositoryFact.Payload["source_run_id"])
	}
	importsMap, ok := repositoryFact.Payload["imports_map"].(map[string][]string)
	if !ok {
		t.Fatalf("repository fact imports_map = %#v, want map[string][]string", repositoryFact.Payload["imports_map"])
	}
	if got, want := importsMap["Worker"][0], firstRepoPath+"/app.py"; got != want {
		t.Fatalf("repository fact imports_map Worker path = %q, want %q", got, want)
	}

	fileFact := fullFacts[1]
	if got, want := fileFact.Payload["relative_path"], "app.py"; got != want {
		t.Fatalf("file fact relative_path = %#v, want %#v", got, want)
	}
	if _, ok := fileFact.Payload["parsed_file_data"]; !ok {
		t.Fatal("file fact parsed_file_data missing, want present")
	}

	entityFact := fullFacts[3]
	if got, want := entityFact.Payload["entity_id"], "content-entity:e_fn123456789"; got != want {
		t.Fatalf("entity fact entity_id = %#v, want %#v", got, want)
	}
	if got, want := entityFact.Payload["entity_type"], "Function"; got != want {
		t.Fatalf("entity fact entity_type = %#v, want %#v", got, want)
	}
	if got, want := entityFact.Payload["source_cache"], "def handler():\n    return 1\n"; got != want {
		t.Fatalf("entity fact source_cache = %#v, want %#v", got, want)
	}
	entityMetadata, ok := entityFact.Payload["entity_metadata"].(map[string]any)
	if !ok {
		t.Fatalf("entity fact entity_metadata = %T, want map[string]any", entityFact.Payload["entity_metadata"])
	}
	if got, want := entityMetadata["docstring"], "Handles requests."; got != want {
		t.Fatalf("entity fact entity_metadata[docstring] = %#v, want %#v", got, want)
	}

	sharedFollowupKinds := []string{emptyFacts[1].FactKind, emptyFacts[2].FactKind}
	if sharedFollowupKinds[0] != "shared_followup" || sharedFollowupKinds[1] != "shared_followup" {
		t.Fatalf("empty repo followup kinds = %v, want both shared_followup", sharedFollowupKinds)
	}

	// Validate empty repo has repo + workload/code-call followups.
	if got, want := len(emptyFacts), 3; got != want {
		t.Fatalf("len(empty facts) = %d, want %d", got, want)
	}

	if got, want := selector.calls, 1; got != want {
		t.Fatalf("selector calls = %d, want %d", got, want)
	}
	gotCalls := make([]string, len(snapshotter.calls))
	copy(gotCalls, snapshotter.calls)
	sort.Strings(gotCalls)
	wantCalls := []string{firstRepoPath, secondRepoPath}
	sort.Strings(wantCalls)
	if !equalStrings(gotCalls, wantCalls) {
		t.Fatalf("snapshotter calls = %v, want %v (order-independent)", snapshotter.calls, wantCalls)
	}
}

func TestGitSourceNextReturnsEmptyWhenSelectionBatchIsEmpty(t *testing.T) {
	t.Parallel()

	source := &GitSource{
		Component: "collector-git",
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt:   time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC),
				Repositories: nil,
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{snapshots: map[string]RepositorySnapshot{}},
	}

	_, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next() error = %v, want nil", err)
	}
	if ok {
		t.Fatal("Next() ok = true, want false")
	}
}

func TestGitSourceNextEmitsDependencyOwnershipForDependencyRepositories(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	repoPath := t.TempDir()
	source := &GitSource{
		Component: "bootstrap-index",
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{
					{
						RepoPath:     repoPath,
						IsDependency: true,
						DisplayName:  "@scope/service-lib",
						Language:     "typescript",
					},
				},
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{
			snapshots: map[string]RepositorySnapshot{
				repoPath: {
					RepoPath:  repoPath,
					FileCount: 1,
					FileData: []map[string]any{{
						"path":          repoPath + "/index.ts",
						"lang":          "typescript",
						"is_dependency": true,
						"functions":     []any{},
						"classes":       []any{},
						"variables":     []any{},
						"imports":       []any{},
					}},
				},
			},
		},
	}

	collected, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next() ok = false, want true")
	}
	if got, want := collected.Scope.Metadata["repo_name"], "@scope/service-lib"; got != want {
		t.Fatalf("scope repo_name = %q, want %q", got, want)
	}

	facts := drainFactChannel(collected.Facts)

	if got, want := facts[0].Payload["is_dependency"], true; got != want {
		t.Fatalf("repository fact is_dependency = %#v, want %#v", got, want)
	}
	if got, want := facts[1].Payload["is_dependency"], true; got != want {
		t.Fatalf("file fact is_dependency = %#v, want %#v", got, want)
	}
}

func TestGitSourceNextDoesNotBufferPartialResultsWhenSnapshottingFails(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	firstRepoPath := t.TempDir()
	secondRepoPath := t.TempDir()
	source := &GitSource{
		Component: "collector-git",
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{
					{RepoPath: firstRepoPath, RemoteURL: "https://github.com/example/one"},
					{RepoPath: secondRepoPath, RemoteURL: "https://github.com/example/two"},
				},
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{
			snapshots: map[string]RepositorySnapshot{
				firstRepoPath: {RepoPath: firstRepoPath, FileCount: 1},
			},
			errForRepoPath: map[string]error{
				secondRepoPath: errors.New("boom"),
			},
		},
	}

	// With streaming, the first repo may succeed before the second fails.
	// Drain all results and verify at least one error surfaces.
	var gotErr error
	for {
		_, ok, err := source.Next(context.Background())
		if err != nil {
			gotErr = err
			break
		}
		if !ok {
			break
		}
	}
	if gotErr == nil {
		t.Fatal("expected error from failing snapshot, got nil")
	}
}

type stubRepositorySelector struct {
	batches []SelectionBatch
	calls   int
}

func (s *stubRepositorySelector) SelectRepositories(context.Context) (SelectionBatch, error) {
	if s.calls >= len(s.batches) {
		s.calls++
		return SelectionBatch{}, nil
	}

	batch := s.batches[s.calls]
	s.calls++
	return batch, nil
}

type stubRepositorySnapshotter struct {
	snapshots      map[string]RepositorySnapshot
	errForRepoPath map[string]error
	calls          []string
	mu             sync.Mutex
}

func (s *stubRepositorySnapshotter) SnapshotRepository(
	_ context.Context,
	repository SelectedRepository,
) (RepositorySnapshot, error) {
	s.mu.Lock()
	s.calls = append(s.calls, repository.RepoPath)
	s.mu.Unlock()

	if err := s.errForRepoPath[repository.RepoPath]; err != nil {
		return RepositorySnapshot{}, err
	}
	snapshot, ok := s.snapshots[repository.RepoPath]
	if !ok {
		return RepositorySnapshot{}, nil
	}
	return snapshot, nil
}

func equalStrings(got, want []string) bool {
	if len(got) != len(want) {
		return false
	}
	for i := range got {
		if got[i] != want[i] {
			return false
		}
	}
	return true
}

func TestBuildCollectedConcurrent(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 14, 10, 0, 0, 0, time.UTC)
	repo1 := t.TempDir()
	repo2 := t.TempDir()
	repo3 := t.TempDir()

	snapshotter := &stubRepositorySnapshotter{
		snapshots: map[string]RepositorySnapshot{
			repo1: {
				RepoPath:  repo1,
				RemoteURL: "https://github.com/example/repo1",
				FileCount: 5,
			},
			repo2: {
				RepoPath:  repo2,
				RemoteURL: "https://github.com/example/repo2",
				FileCount: 3,
			},
			repo3: {
				RepoPath:  repo3,
				RemoteURL: "https://github.com/example/repo3",
				FileCount: 7,
			},
		},
	}

	source := &GitSource{
		Component:       "collector-git",
		SnapshotWorkers: 2,
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{
					{RepoPath: repo1, RemoteURL: "https://github.com/example/repo1"},
					{RepoPath: repo2, RemoteURL: "https://github.com/example/repo2"},
					{RepoPath: repo3, RemoteURL: "https://github.com/example/repo3"},
				},
			}},
		},
		Snapshotter: snapshotter,
	}

	// Collect all generations
	var collected []CollectedGeneration
	for {
		gen, ok, err := source.Next(context.Background())
		if err != nil {
			t.Fatalf("Next() error = %v, want nil", err)
		}
		if !ok {
			break
		}
		collected = append(collected, gen)
	}

	if got, want := len(collected), 3; got != want {
		t.Fatalf("collected count = %d, want %d", got, want)
	}

	// Verify all repos were snapshotted
	snapshotter.mu.Lock()
	snapshotCalls := len(snapshotter.calls)
	snapshotter.mu.Unlock()

	if got, want := snapshotCalls, 3; got != want {
		t.Fatalf("snapshot calls = %d, want %d", got, want)
	}

	// Verify each generation has the expected structure
	for _, gen := range collected {
		if gen.Scope.SourceSystem != "git" {
			t.Errorf("Scope.SourceSystem = %q, want %q", gen.Scope.SourceSystem, "git")
		}
		if string(gen.Scope.ScopeKind) != "repository" {
			t.Errorf("Scope.ScopeKind = %q, want %q", gen.Scope.ScopeKind, "repository")
		}
		facts := drainFactChannel(gen.Facts)
		if len(facts) < 2 {
			t.Errorf("Facts count = %d, want >= 2", len(facts))
		}
	}
}

func TestBuildCollectedConcurrentHandlesErrors(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 14, 10, 0, 0, 0, time.UTC)
	repo1 := t.TempDir()
	repo2 := t.TempDir()

	snapshotter := &stubRepositorySnapshotter{
		snapshots: map[string]RepositorySnapshot{
			repo1: {RepoPath: repo1, FileCount: 1},
		},
		errForRepoPath: map[string]error{
			repo2: errors.New("snapshot failed"),
		},
	}

	source := &GitSource{
		Component:       "collector-git",
		SnapshotWorkers: 2,
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{
					{RepoPath: repo1},
					{RepoPath: repo2},
				},
			}},
		},
		Snapshotter: snapshotter,
	}

	// With streaming, the first repo may succeed before the second fails.
	var gotErr error
	for {
		_, ok, err := source.Next(context.Background())
		if err != nil {
			gotErr = err
			break
		}
		if !ok {
			break
		}
	}
	if gotErr == nil {
		t.Fatal("expected error from failing snapshot, got nil")
	}
}

func TestGitSourceStreamingSequentialFallback(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 14, 10, 0, 0, 0, time.UTC)
	repo1 := t.TempDir()
	repo2 := t.TempDir()

	source := &GitSource{
		Component:       "collector-git",
		SnapshotWorkers: 0, // sequential fallback
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{
					{RepoPath: repo1, RemoteURL: "https://github.com/example/repo1"},
					{RepoPath: repo2, RemoteURL: "https://github.com/example/repo2"},
				},
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{
			snapshots: map[string]RepositorySnapshot{
				repo1: {RepoPath: repo1, FileCount: 3},
				repo2: {RepoPath: repo2, FileCount: 5},
			},
		},
	}

	var collected []CollectedGeneration
	for {
		gen, ok, err := source.Next(context.Background())
		if err != nil {
			t.Fatalf("Next() error = %v, want nil", err)
		}
		if !ok {
			break
		}
		collected = append(collected, gen)
	}

	if got, want := len(collected), 2; got != want {
		t.Fatalf("collected count = %d, want %d", got, want)
	}
}

func TestGitSourceStreamingCancellation(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 14, 10, 0, 0, 0, time.UTC)
	repos := make([]SelectedRepository, 20)
	snapshots := make(map[string]RepositorySnapshot)
	for i := range repos {
		dir := t.TempDir()
		repos[i] = SelectedRepository{RepoPath: dir}
		snapshots[dir] = RepositorySnapshot{RepoPath: dir, FileCount: 1}
	}

	source := &GitSource{
		Component:       "collector-git",
		SnapshotWorkers: 4,
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt:   observedAt,
				Repositories: repos,
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{snapshots: snapshots},
	}

	ctx, cancel := context.WithCancel(context.Background())
	// Read one generation, then cancel
	_, ok, err := source.Next(ctx)
	if err != nil {
		t.Fatalf("first Next() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("first Next() ok = false, want true")
	}

	cancel()

	// Subsequent calls should return context.Canceled or drain cleanly
	for {
		_, ok, err := source.Next(ctx)
		if err != nil {
			break // expected: context cancelled
		}
		if !ok {
			break
		}
	}
}

func TestGitSourceStreamResetsBetweenBatches(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 14, 10, 0, 0, 0, time.UTC)
	repo1 := t.TempDir()
	repo2 := t.TempDir()

	source := &GitSource{
		Component:       "collector-git",
		SnapshotWorkers: 1,
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{
				{
					ObservedAt:   observedAt,
					Repositories: []SelectedRepository{{RepoPath: repo1}},
				},
				{
					ObservedAt:   observedAt.Add(time.Minute),
					Repositories: []SelectedRepository{{RepoPath: repo2}},
				},
			},
		},
		Snapshotter: &stubRepositorySnapshotter{
			snapshots: map[string]RepositorySnapshot{
				repo1: {RepoPath: repo1, FileCount: 1},
				repo2: {RepoPath: repo2, FileCount: 2},
			},
		},
	}

	// First batch: one repo
	gen1, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("batch1 Next() error = %v", err)
	}
	if !ok {
		t.Fatal("batch1 Next() ok = false, want true")
	}

	// Drain first batch
	_, ok, err = source.Next(context.Background())
	if err != nil {
		t.Fatalf("batch1 drain error = %v", err)
	}
	if ok {
		t.Fatal("batch1 should be exhausted")
	}

	// Second batch: should trigger fresh discovery
	gen2, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("batch2 Next() error = %v", err)
	}
	if !ok {
		t.Fatal("batch2 Next() ok = false, want true")
	}

	if gen1.Scope.ScopeID == gen2.Scope.ScopeID {
		t.Fatal("expected different scopes across batches")
	}
}

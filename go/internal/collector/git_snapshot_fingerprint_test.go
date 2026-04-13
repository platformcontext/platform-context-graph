package collector

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/repositoryidentity"
)

func TestBuildCollectedGenerationDerivesStableFreshnessHintForEquivalentSnapshots(t *testing.T) {
	t.Parallel()

	repoPath := t.TempDir()
	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	sourceRunID := "source-run-123"
	repo := testCollectorRepositoryMetadata(repoPath)
	snapshotA := testCollectorSnapshot(repoPath, "def handler():\n    return 1\n", "digest-1")
	snapshotB := testCollectorSnapshot(repoPath, "def handler():\n    return 1\n", "digest-1")

	collectedA := buildCollectedGeneration(repoPath, repo, sourceRunID, observedAt, snapshotA)
	collectedB := buildCollectedGeneration(repoPath, repo, sourceRunID, observedAt, snapshotB)

	if got, want := collectedA.Generation.FreshnessHint, collectedB.Generation.FreshnessHint; got != want {
		t.Fatalf("FreshnessHint mismatch for equivalent snapshots: got %q, want %q", got, want)
	}
	if got, want := collectedA.Generation.GenerationID, collectedB.Generation.GenerationID; got != want {
		t.Fatalf("GenerationID mismatch for equivalent snapshots: got %q, want %q", got, want)
	}
	if got, want := len(collectedA.Facts), len(collectedB.Facts); got != want {
		t.Fatalf("Fact count mismatch for equivalent snapshots: got %d, want %d", got, want)
	}
}

func TestBuildCollectedGenerationChangesFreshnessHintForMateriallyDifferentSnapshots(t *testing.T) {
	t.Parallel()

	repoPath := t.TempDir()
	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	sourceRunID := "source-run-123"
	repo := testCollectorRepositoryMetadata(repoPath)
	snapshotA := testCollectorSnapshot(repoPath, "def handler():\n    return 1\n", "digest-1")
	snapshotB := testCollectorSnapshot(repoPath, "def handler():\n    return 2\n", "digest-2")

	collectedA := buildCollectedGeneration(repoPath, repo, sourceRunID, observedAt, snapshotA)
	collectedB := buildCollectedGeneration(repoPath, repo, sourceRunID, observedAt, snapshotB)

	if got, want := collectedA.Generation.FreshnessHint, collectedB.Generation.FreshnessHint; got == want {
		t.Fatalf("FreshnessHint = %q for materially different snapshots, want different values", got)
	}
}

func TestGitSourceNextKeepsGenerationAndFactsStableAcrossSnapshotChanges(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	repoPath := t.TempDir()
	firstSnapshot := testCollectorSnapshot(repoPath, "def handler():\n    return 1\n", "digest-1")
	secondSnapshot := testCollectorSnapshot(repoPath, "def handler():\n    return 2\n", "digest-2")

	firstSource := newTestCollectorGitSource(observedAt, repoPath, firstSnapshot)
	secondSource := newTestCollectorGitSource(observedAt, repoPath, secondSnapshot)

	firstCollected, ok, err := firstSource.Next(context.Background())
	if err != nil {
		t.Fatalf("first Next() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("first Next() ok = false, want true")
	}

	secondCollected, ok, err := secondSource.Next(context.Background())
	if err != nil {
		t.Fatalf("second Next() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("second Next() ok = false, want true")
	}

	if got, want := firstCollected.Generation.GenerationID, secondCollected.Generation.GenerationID; got != want {
		t.Fatalf("GenerationID = %q, want %q", got, want)
	}
	if got, want := firstCollected.Generation.FreshnessHint, secondCollected.Generation.FreshnessHint; got == want {
		t.Fatalf("FreshnessHint = %q for changed snapshot, want different values", got)
	}
	if got, want := len(firstCollected.Facts), len(secondCollected.Facts); got != want {
		t.Fatalf("Fact count = %d, want %d", got, want)
	}
	if got, want := firstCollected.Facts[0].FactID, secondCollected.Facts[0].FactID; got != want {
		t.Fatalf("repository fact ID = %q, want %q", got, want)
	}
	if got, want := firstCollected.Facts[2].FactID, secondCollected.Facts[2].FactID; got != want {
		t.Fatalf("content fact ID = %q, want %q", got, want)
	}
	if got, want := firstCollected.Facts[2].Payload["content_body"], "def handler():\n    return 1\n"; got != want {
		t.Fatalf("first content body = %#v, want %#v", got, want)
	}
	if got, want := secondCollected.Facts[2].Payload["content_body"], "def handler():\n    return 2\n"; got != want {
		t.Fatalf("second content body = %#v, want %#v", got, want)
	}
}

func newTestCollectorGitSource(
	observedAt time.Time,
	repoPath string,
	snapshot RepositorySnapshot,
) *GitSource {
	return &GitSource{
		Component: "collector-git",
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{{
					RepoPath:  repoPath,
					RemoteURL: "https://github.com/example/service",
				}},
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{
			snapshots: map[string]RepositorySnapshot{
				repoPath: snapshot,
			},
		},
	}
}

func testCollectorRepositoryMetadata(repoPath string) repositoryidentity.Metadata {
	return repositoryidentity.Metadata{
		ID:        "repository:r_12345678",
		Name:      "example-service",
		RepoSlug:  "example/service",
		RemoteURL: "https://github.com/example/service",
		LocalPath: repoPath,
		HasRemote: true,
	}
}

func testCollectorSnapshot(repoPath string, body string, digest string) RepositorySnapshot {
	return RepositorySnapshot{
		FileCount: 1,
		FileData: []map[string]any{
			{
				"lang": "python",
				"path": repoPath + "/app.py",
				"functions": []any{
					map[string]any{
						"name":        "handler",
						"line_number": 1,
						"uid":         "content-entity:e_fn123456789",
					},
				},
			},
		},
		ContentFiles: []ContentFileSnapshot{{
			RelativePath: "app.py",
			Body:         body,
			Digest:       digest,
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
			SourceCache:  body,
			IndexedAt:    time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC),
		}},
	}
}

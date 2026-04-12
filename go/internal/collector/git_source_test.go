package collector

import (
	"context"
	"testing"
	"time"
)

func TestGitSourceNextBuildsCollectedGenerationFromSnapshotBatch(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	repoPath := t.TempDir()
	runner := &stubSnapshotRunner{
		batches: []SnapshotBatch{{
			ObservedAt: observedAt,
			Repositories: []RepositorySnapshot{{
				RepoPath:  repoPath,
				RemoteURL: "https://github.com/example/service",
				FileCount: 1,
				FileData: []map[string]any{{
					"path": repoPath + "/app.py",
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
				}},
			}},
		}},
	}

	source := &GitSource{
		Component: "collector-git",
		Runner:    runner,
	}

	collected, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next() ok = false, want true")
	}
	if got, want := collected.Scope.SourceSystem, "git"; got != want {
		t.Fatalf("Scope.SourceSystem = %q, want %q", got, want)
	}
	if got, want := string(collected.Scope.ScopeKind), "repository"; got != want {
		t.Fatalf("Scope.ScopeKind = %q, want %q", got, want)
	}
	if got, want := string(collected.Generation.TriggerKind), "snapshot"; got != want {
		t.Fatalf("Generation.TriggerKind = %q, want %q", got, want)
	}
	if got, want := len(collected.Facts), 5; got != want {
		t.Fatalf("len(Facts) = %d, want %d", got, want)
	}

	wantKinds := []string{
		"repository",
		"file",
		"content",
		"content_entity",
		"shared_followup",
	}
	for i, want := range wantKinds {
		if got := collected.Facts[i].FactKind; got != want {
			t.Fatalf("Facts[%d].FactKind = %q, want %q", i, got, want)
		}
	}

	fileFact := collected.Facts[1]
	if got, want := fileFact.Payload["relative_path"], "app.py"; got != want {
		t.Fatalf("file fact relative_path = %#v, want %#v", got, want)
	}
	if _, ok := fileFact.Payload["parsed_file_data"]; !ok {
		t.Fatal("file fact parsed_file_data missing, want present")
	}

	entityFact := collected.Facts[3]
	if got, want := entityFact.Payload["entity_id"], "content-entity:e_fn123456789"; got != want {
		t.Fatalf("entity fact entity_id = %#v, want %#v", got, want)
	}
	if got, want := entityFact.Payload["entity_type"], "Function"; got != want {
		t.Fatalf("entity fact entity_type = %#v, want %#v", got, want)
	}
	if got, want := entityFact.Payload["source_cache"], "def handler():\n    return 1\n"; got != want {
		t.Fatalf("entity fact source_cache = %#v, want %#v", got, want)
	}
}

func TestGitSourceNextReturnsEmptyWhenSnapshotBatchIsEmpty(t *testing.T) {
	t.Parallel()

	source := &GitSource{
		Component: "collector-git",
		Runner: &stubSnapshotRunner{
			batches: []SnapshotBatch{{
				ObservedAt:   time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC),
				Repositories: nil,
			}},
		},
	}

	_, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next() error = %v, want nil", err)
	}
	if ok {
		t.Fatal("Next() ok = true, want false")
	}
}

type stubSnapshotRunner struct {
	batches []SnapshotBatch
	calls   int
}

func (s *stubSnapshotRunner) CollectSnapshots(context.Context) (SnapshotBatch, error) {
	if s.calls >= len(s.batches) {
		s.calls++
		return SnapshotBatch{}, nil
	}

	batch := s.batches[s.calls]
	s.calls++
	return batch, nil
}

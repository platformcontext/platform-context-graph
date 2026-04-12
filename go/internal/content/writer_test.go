package content

import (
	"context"
	"testing"
)

func TestMaterializationScopeGenerationKey(t *testing.T) {
	t.Parallel()

	got := Materialization{
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
	}

	if want := "scope-123:generation-456"; got.ScopeGenerationKey() != want {
		t.Fatalf("Materialization.ScopeGenerationKey() = %q, want %q", got.ScopeGenerationKey(), want)
	}
}

func TestMaterializationCloneCopiesRecords(t *testing.T) {
	t.Parallel()

	original := Materialization{
		RepoID:       "repository:r_12345678",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		Records: []Record{
			{
				Path:     "README.md",
				Body:     "hello",
				Digest:   "digest-1",
				Deleted:  false,
				Metadata: map[string]string{"language": "markdown"},
			},
		},
	}

	cloned := original.Clone()
	if got, want := cloned.RepoID, "repository:r_12345678"; got != want {
		t.Fatalf("cloned RepoID = %q, want %q", got, want)
	}
	cloned.Records[0].Metadata["language"] = "mutated"

	if got, want := original.Records[0].Metadata["language"], "markdown"; got != want {
		t.Fatalf("original record metadata = %q, want %q", got, want)
	}
}

func TestMemoryWriterStoresClone(t *testing.T) {
	t.Parallel()

	writer := &MemoryWriter{}
	got, err := writer.Write(context.Background(), Materialization{
		RepoID:       "repository:r_12345678",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		Records: []Record{{
			Path:   "README.md",
			Body:   "hello",
			Digest: "digest-1",
		}},
	})
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got.RecordCount != 1 {
		t.Fatalf("Write().RecordCount = %d, want 1", got.RecordCount)
	}
	if got, want := writer.Writes[0].RepoID, "repository:r_12345678"; got != want {
		t.Fatalf("stored RepoID = %q, want %q", got, want)
	}
}

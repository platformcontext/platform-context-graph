package postgres

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
)

func TestContentWriterBatchesFileInserts(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{}
	writer := NewContentWriter(db)
	writer.Now = func() time.Time { return time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC) }

	// Create 3 file records (small batch, should result in 1 query)
	records := []content.Record{
		{Path: "file1.go", Body: "content1", Metadata: map[string]string{"language": "go"}},
		{Path: "file2.go", Body: "content2", Metadata: map[string]string{"language": "go"}},
		{Path: "file3.go", Body: "content3", Metadata: map[string]string{"language": "go"}},
	}

	mat := content.Materialization{
		RepoID:       "test-repo",
		ScopeID:      "test-scope",
		GenerationID: "test-gen",
		Records:      records,
	}

	result, err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got, want := result.RecordCount, 3; got != want {
		t.Fatalf("RecordCount = %d, want %d", got, want)
	}

	// Should have exactly 1 exec call (batched insert)
	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d (batched)", got, want)
	}

	// Query should be a multi-row INSERT
	query := db.execs[0].query
	if !strings.Contains(query, "INSERT INTO content_files") {
		t.Fatalf("query should contain content_files insert: %s", query)
	}
	// Count the number of value placeholders - should have 3 sets
	valueGroups := strings.Count(query, "($")
	if got, want := valueGroups, 3; got != want {
		t.Fatalf("value groups = %d, want %d (one per record)", got, want)
	}
}

func TestContentWriterBatchesEntityInserts(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{}
	writer := NewContentWriter(db)
	writer.Now = func() time.Time { return time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC) }

	// Create 2 entity records
	entities := []content.EntityRecord{
		{
			EntityID:   "entity-1",
			Path:       "main.go",
			EntityType: "function",
			EntityName: "main",
			StartLine:  1,
			EndLine:    10,
		},
		{
			EntityID:   "entity-2",
			Path:       "util.go",
			EntityType: "function",
			EntityName: "helper",
			StartLine:  5,
			EndLine:    15,
		},
	}

	mat := content.Materialization{
		RepoID:       "test-repo",
		ScopeID:      "test-scope",
		GenerationID: "test-gen",
		Entities:     entities,
	}

	result, err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got, want := result.EntityCount, 2; got != want {
		t.Fatalf("EntityCount = %d, want %d", got, want)
	}

	// Should have exactly 1 exec call (batched insert)
	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d (batched)", got, want)
	}

	// Query should be a multi-row INSERT
	query := db.execs[0].query
	if !strings.Contains(query, "INSERT INTO content_entities") {
		t.Fatalf("query should contain content_entities insert: %s", query)
	}
	valueGroups := strings.Count(query, "($")
	if got, want := valueGroups, 2; got != want {
		t.Fatalf("value groups = %d, want %d (one per entity)", got, want)
	}
}

func TestContentWriterDeletesAreNotBatched(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{}
	writer := NewContentWriter(db)
	writer.Now = func() time.Time { return time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC) }

	// Create 1 deleted record
	records := []content.Record{
		{Path: "deleted.go", Deleted: true},
	}

	mat := content.Materialization{
		RepoID:       "test-repo",
		ScopeID:      "test-scope",
		GenerationID: "test-gen",
		Records:      records,
	}

	result, err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got, want := result.DeletedCount, 1; got != want {
		t.Fatalf("DeletedCount = %d, want %d", got, want)
	}

	// Deletes should result in 2 exec calls (entity delete + file delete)
	if got, want := len(db.execs), 2; got != want {
		t.Fatalf("exec count = %d, want %d (2 deletes)", got, want)
	}
	if !strings.Contains(db.execs[0].query, "DELETE FROM content_entities") {
		t.Fatalf("first query should delete entities: %s", db.execs[0].query)
	}
	if !strings.Contains(db.execs[1].query, "DELETE FROM content_files") {
		t.Fatalf("second query should delete files: %s", db.execs[1].query)
	}
}

func TestContentWriterBatchesLargeFileSet(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{}
	writer := NewContentWriter(db)
	writer.Now = func() time.Time { return time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC) }

	// Create 1000 file records (should result in 2 batches: 500 + 500)
	records := make([]content.Record, 1000)
	for i := 0; i < 1000; i++ {
		records[i] = content.Record{
			Path:     "file" + strings.Repeat("x", i%10) + ".go",
			Body:     "content" + strings.Repeat("x", i%10),
			Metadata: map[string]string{"language": "go"},
		}
	}

	mat := content.Materialization{
		RepoID:       "test-repo",
		ScopeID:      "test-scope",
		GenerationID: "test-gen",
		Records:      records,
	}

	result, err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got, want := result.RecordCount, 1000; got != want {
		t.Fatalf("RecordCount = %d, want %d", got, want)
	}

	// Should have exactly 2 exec calls (2 batches of 500)
	if got, want := len(db.execs), 2; got != want {
		t.Fatalf("exec count = %d, want %d (2 batches)", got, want)
	}

	// Both queries should be multi-row INSERTs
	for i, exec := range db.execs {
		if !strings.Contains(exec.query, "INSERT INTO content_files") {
			t.Fatalf("query %d should contain content_files insert", i)
		}
		valueGroups := strings.Count(exec.query, "($")
		if got, want := valueGroups, 500; got != want {
			t.Fatalf("batch %d: value groups = %d, want %d", i, got, want)
		}
	}
}

func TestContentWriterBatchesLargeEntitySet(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{}
	writer := NewContentWriter(db)
	writer.Now = func() time.Time { return time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC) }

	// Create 600 entity records (should result in 2 batches: 300 + 300)
	entities := make([]content.EntityRecord, 600)
	for i := 0; i < 600; i++ {
		entities[i] = content.EntityRecord{
			EntityID:   "entity-" + strings.Repeat("x", i%10),
			Path:       "file.go",
			EntityType: "function",
			EntityName: "func" + strings.Repeat("x", i%10),
			StartLine:  i + 1,
			EndLine:    i + 10,
		}
	}

	mat := content.Materialization{
		RepoID:       "test-repo",
		ScopeID:      "test-scope",
		GenerationID: "test-gen",
		Entities:     entities,
	}

	result, err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v, want nil", err)
	}
	if got, want := result.EntityCount, 600; got != want {
		t.Fatalf("EntityCount = %d, want %d", got, want)
	}

	// Should have exactly 2 exec calls (2 batches of 300)
	if got, want := len(db.execs), 2; got != want {
		t.Fatalf("exec count = %d, want %d (2 batches)", got, want)
	}

	// Both queries should be multi-row INSERTs
	for i, exec := range db.execs {
		if !strings.Contains(exec.query, "INSERT INTO content_entities") {
			t.Fatalf("query %d should contain content_entities insert", i)
		}
		valueGroups := strings.Count(exec.query, "($")
		if got, want := valueGroups, 300; got != want {
			t.Fatalf("batch %d: value groups = %d, want %d", i, got, want)
		}
	}
}

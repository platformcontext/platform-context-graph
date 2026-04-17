package postgres

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBootstrapDefinitionsAreOrderedAndComplete(t *testing.T) {
	t.Parallel()

	defs := BootstrapDefinitions()
	if len(defs) != 12 {
		t.Fatalf("BootstrapDefinitions() len = %d, want 12", len(defs))
	}

	wantNames := []string{
		"ingestion_scopes",
		"scope_generations",
		"fact_records",
		"content_store",
		"fact_work_items",
		"fact_work_item_audit",
		"projection_decisions",
		"shared_projection_intents",
		"runtime_ingester_control",
		"relationship_tables",
		"shared_projection_acceptance",
		"graph_projection_phase_state",
	}
	for i, want := range wantNames {
		if defs[i].Name != want {
			t.Fatalf("BootstrapDefinitions()[%d].Name = %q, want %q", i, defs[i].Name, want)
		}
	}

	for _, def := range defs {
		if strings.TrimSpace(def.Path) == "" {
			t.Fatalf("definition %q has empty path", def.Name)
		}
		if strings.TrimSpace(def.SQL) == "" {
			t.Fatalf("definition %q has empty SQL", def.Name)
		}
	}
}

func TestBootstrapDefinitionsIncludeContentStoreTables(t *testing.T) {
	t.Parallel()

	var contentStore Definition
	for _, def := range BootstrapDefinitions() {
		if def.Name == "content_store" {
			contentStore = def
			break
		}
	}
	if contentStore.Name == "" {
		t.Fatal("content_store definition missing")
	}
	if !strings.Contains(contentStore.SQL, "CREATE TABLE IF NOT EXISTS content_files") {
		t.Fatal("content_store SQL missing content_files table")
	}
	if !strings.Contains(contentStore.SQL, "CREATE TABLE IF NOT EXISTS content_entities") {
		t.Fatal("content_store SQL missing content_entities table")
	}
	if !strings.Contains(contentStore.SQL, "metadata JSONB NOT NULL DEFAULT '{}'::jsonb") {
		t.Fatal("content_store SQL missing content_entities metadata jsonb column")
	}
}

func TestApplyBootstrapExecutesDefinitionsInOrder(t *testing.T) {
	t.Parallel()

	exec := &recordingExecutor{}
	if err := ApplyBootstrap(context.Background(), exec); err != nil {
		t.Fatalf("ApplyBootstrap() error = %v, want nil", err)
	}

	got := exec.statements
	defs := BootstrapDefinitions()
	want := make([]string, 0, len(defs))
	for _, def := range defs {
		want = append(want, def.SQL)
	}
	if len(got) != len(want) {
		t.Fatalf("ApplyBootstrap() executed %d statements, want %d", len(got), len(want))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("statement[%d] mismatch\n got: %q\nwant: %q", i, got[i], want[i])
		}
	}
}

func TestBootstrapSQLFilesMirrorDefinitions(t *testing.T) {
	t.Parallel()

	repoRoot := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	for _, def := range BootstrapDefinitions() {
		path := filepath.Join(repoRoot, def.Path)
		got, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("ReadFile(%q) error = %v", path, err)
		}
		if strings.TrimSpace(string(got)) != strings.TrimSpace(def.SQL) {
			t.Fatalf("file %q does not match bootstrap definition %q", path, def.Name)
		}
	}
}

func TestValidateDefinitionsRejectsBlankValues(t *testing.T) {
	t.Parallel()

	err := ValidateDefinitions([]Definition{{Name: " ", Path: "x.sql", SQL: "SELECT 1;"}})
	if err == nil {
		t.Fatal("ValidateDefinitions() error = nil, want non-nil")
	}
}

type recordingExecutor struct {
	statements []string
}

func (e *recordingExecutor) ExecContext(_ context.Context, statement string, _ ...any) (sql.Result, error) {
	e.statements = append(e.statements, statement)
	return result{}, nil
}

type result struct{}

func (result) LastInsertId() (int64, error) { return 0, nil }

func (result) RowsAffected() (int64, error) { return 0, nil }

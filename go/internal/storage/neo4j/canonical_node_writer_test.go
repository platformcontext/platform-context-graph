package neo4j

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
)

// mockExecutor records all Execute() calls in order for assertion.
type mockExecutor struct {
	calls []Statement
	err   error // optional error to return
}

func (m *mockExecutor) Execute(_ context.Context, stmt Statement) error {
	m.calls = append(m.calls, stmt)
	return m.err
}

func TestCanonicalNodeWriterWritePhaseOrder(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID:    "repo-1",
			Name:      "my-repo",
			Path:      "/repos/my-repo",
			LocalPath: "/repos/my-repo",
			RemoteURL: "https://github.com/org/my-repo",
			RepoSlug:  "org/my-repo",
			HasRemote: true,
		},
		Directories: []projector.DirectoryRow{
			{Path: "/repos/my-repo/src", Name: "src", ParentPath: "/repos/my-repo", RepoID: "repo-1", Depth: 0},
		},
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", Name: "main.go", Language: "go", RepoID: "repo-1", DirPath: "/repos/my-repo/src"},
		},
		Entities: []projector.EntityRow{
			{EntityID: "e1", Label: "Function", EntityName: "main", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 5, EndLine: 10, Language: "go", RepoID: "repo-1"},
		},
		Modules: []projector.ModuleRow{
			{Name: "fmt", Language: "go"},
		},
		Imports: []projector.ImportRow{
			{FilePath: "/repos/my-repo/src/main.go", ModuleName: "fmt", ImportedName: "fmt", LineNumber: 3},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	if len(exec.calls) == 0 {
		t.Fatal("expected executor calls, got 0")
	}

	// Verify strict phase order: retract phases first, then repository, directories, files, entities, modules, structural edges.
	// Find the phase boundaries by inspecting operation types and cypher content.
	phaseOrder := []string{}
	for _, call := range exec.calls {
		switch call.Operation {
		case OperationCanonicalRetract:
			if len(phaseOrder) == 0 || phaseOrder[len(phaseOrder)-1] != "retract" {
				phaseOrder = append(phaseOrder, "retract")
			}
		case OperationCanonicalUpsert:
			if strings.Contains(call.Cypher, "MERGE (r:Repository") {
				phaseOrder = append(phaseOrder, "repository")
			} else if strings.Contains(call.Cypher, "MERGE (d:Directory") {
				if len(phaseOrder) == 0 || phaseOrder[len(phaseOrder)-1] != "directories" {
					phaseOrder = append(phaseOrder, "directories")
				}
			} else if strings.Contains(call.Cypher, "MERGE (f:File") {
				if len(phaseOrder) == 0 || phaseOrder[len(phaseOrder)-1] != "files" {
					phaseOrder = append(phaseOrder, "files")
				}
			} else if strings.Contains(call.Cypher, "MERGE (n:Function") || strings.Contains(call.Cypher, "MERGE (n:Class") {
				if len(phaseOrder) == 0 || phaseOrder[len(phaseOrder)-1] != "entities" {
					phaseOrder = append(phaseOrder, "entities")
				}
			} else if strings.Contains(call.Cypher, "MERGE (m:Module") {
				if len(phaseOrder) == 0 || phaseOrder[len(phaseOrder)-1] != "modules" {
					phaseOrder = append(phaseOrder, "modules")
				}
			} else if strings.Contains(call.Cypher, "IMPORTS") || strings.Contains(call.Cypher, "HAS_PARAMETER") || strings.Contains(call.Cypher, "CONTAINS") {
				if len(phaseOrder) == 0 || phaseOrder[len(phaseOrder)-1] != "structural_edges" {
					phaseOrder = append(phaseOrder, "structural_edges")
				}
			}
		}
	}

	expected := []string{"retract", "repository", "directories", "files", "entities", "modules", "structural_edges"}
	if len(phaseOrder) != len(expected) {
		t.Fatalf("phase order = %v, want %v", phaseOrder, expected)
	}
	for i := range expected {
		if phaseOrder[i] != expected[i] {
			t.Fatalf("phase[%d] = %q, want %q (full order: %v)", i, phaseOrder[i], expected[i], phaseOrder)
		}
	}
}

func TestCanonicalNodeWriterDirectoryDepthOrder(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-1",
			Name:   "my-repo",
			Path:   "/repos/my-repo",
		},
		Directories: []projector.DirectoryRow{
			{Path: "/repos/my-repo/src/pkg/sub", Name: "sub", ParentPath: "/repos/my-repo/src/pkg", RepoID: "repo-1", Depth: 2},
			{Path: "/repos/my-repo/src", Name: "src", ParentPath: "/repos/my-repo", RepoID: "repo-1", Depth: 0},
			{Path: "/repos/my-repo/src/pkg", Name: "pkg", ParentPath: "/repos/my-repo/src", RepoID: "repo-1", Depth: 1},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// Collect directory-phase calls (MERGE (d:Directory ...))
	var dirCalls []Statement
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert && strings.Contains(call.Cypher, "MERGE (d:Directory") {
			dirCalls = append(dirCalls, call)
		}
	}

	if len(dirCalls) == 0 {
		t.Fatal("expected directory calls, got 0")
	}

	// Depth-0 dirs use MATCH (r:Repository ...), depth 1+ use MATCH (p:Directory ...)
	// First call must be depth 0 (Repository parent)
	if !strings.Contains(dirCalls[0].Cypher, "MATCH (r:Repository") {
		t.Fatalf("first directory call should match Repository parent, got: %s", dirCalls[0].Cypher)
	}

	// Subsequent calls must use Directory parent
	for i := 1; i < len(dirCalls); i++ {
		if !strings.Contains(dirCalls[i].Cypher, "MATCH (p:Directory") {
			t.Fatalf("directory call[%d] should match Directory parent, got: %s", i, dirCalls[i].Cypher)
		}
	}
}

func TestCanonicalNodeWriterEntityGroupsByLabel(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-1",
			Name:   "my-repo",
			Path:   "/repos/my-repo",
		},
		Entities: []projector.EntityRow{
			{EntityID: "f1", Label: "Function", EntityName: "foo", FilePath: "/f.go", RelativePath: "f.go", StartLine: 1, EndLine: 5, Language: "go", RepoID: "repo-1"},
			{EntityID: "c1", Label: "Class", EntityName: "Bar", FilePath: "/b.py", RelativePath: "b.py", StartLine: 1, EndLine: 10, Language: "python", RepoID: "repo-1"},
			{EntityID: "f2", Label: "Function", EntityName: "baz", FilePath: "/f.go", RelativePath: "f.go", StartLine: 7, EndLine: 12, Language: "go", RepoID: "repo-1"},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// Collect entity-phase calls
	var entityCalls []Statement
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert &&
			(strings.Contains(call.Cypher, "MERGE (n:Function") || strings.Contains(call.Cypher, "MERGE (n:Class")) {
			entityCalls = append(entityCalls, call)
		}
	}

	if len(entityCalls) != 2 {
		t.Fatalf("expected 2 entity label groups (Function, Class), got %d", len(entityCalls))
	}

	// Verify one UNWIND per label
	for _, call := range entityCalls {
		if !strings.HasPrefix(strings.TrimSpace(call.Cypher), "UNWIND") {
			t.Fatalf("entity call should use UNWIND: %s", call.Cypher)
		}
	}

	// Function group should have 2 rows, Class group should have 1
	funcFound, classFound := false, false
	for _, call := range entityCalls {
		rows := call.Parameters["rows"].([]map[string]any)
		if strings.Contains(call.Cypher, "MERGE (n:Function") {
			funcFound = true
			if len(rows) != 2 {
				t.Fatalf("Function group rows = %d, want 2", len(rows))
			}
		}
		if strings.Contains(call.Cypher, "MERGE (n:Class") {
			classFound = true
			if len(rows) != 1 {
				t.Fatalf("Class group rows = %d, want 1", len(rows))
			}
		}
	}
	if !funcFound {
		t.Fatal("missing Function entity group")
	}
	if !classFound {
		t.Fatal("missing Class entity group")
	}
}

func TestCanonicalNodeWriterBatching(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 2, nil) // batch size = 2

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-1",
			Name:   "my-repo",
			Path:   "/repos/my-repo",
		},
		Files: []projector.FileRow{
			{Path: "/f1.go", RelativePath: "f1.go", Name: "f1.go", Language: "go", RepoID: "repo-1", DirPath: "/src"},
			{Path: "/f2.go", RelativePath: "f2.go", Name: "f2.go", Language: "go", RepoID: "repo-1", DirPath: "/src"},
			{Path: "/f3.go", RelativePath: "f3.go", Name: "f3.go", Language: "go", RepoID: "repo-1", DirPath: "/src"},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// Collect file-phase calls
	var fileCalls []Statement
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert && strings.Contains(call.Cypher, "MERGE (f:File") {
			fileCalls = append(fileCalls, call)
		}
	}

	// 3 files with batch size 2 => 2 batches (2 + 1)
	if len(fileCalls) != 2 {
		t.Fatalf("file batches = %d, want 2", len(fileCalls))
	}

	batch1Rows := fileCalls[0].Parameters["rows"].([]map[string]any)
	batch2Rows := fileCalls[1].Parameters["rows"].([]map[string]any)
	if len(batch1Rows) != 2 {
		t.Fatalf("batch 1 rows = %d, want 2", len(batch1Rows))
	}
	if len(batch2Rows) != 1 {
		t.Fatalf("batch 2 rows = %d, want 1", len(batch2Rows))
	}
}

func TestCanonicalNodeWriterRetraction(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-1",
			Name:   "my-repo",
			Path:   "/repos/my-repo",
		},
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/main.go", RelativePath: "main.go", Name: "main.go", Language: "go", RepoID: "repo-1", DirPath: "/repos/my-repo"},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// First calls should be retraction (OperationCanonicalRetract)
	var retractCalls []Statement
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalRetract {
			retractCalls = append(retractCalls, call)
		}
	}

	if len(retractCalls) == 0 {
		t.Fatal("expected retraction calls, got 0")
	}

	// Retraction calls should all come before any upsert
	lastRetractIdx := -1
	firstUpsertIdx := -1
	for i, call := range exec.calls {
		if call.Operation == OperationCanonicalRetract {
			lastRetractIdx = i
		}
		if call.Operation == OperationCanonicalUpsert && firstUpsertIdx == -1 {
			firstUpsertIdx = i
		}
	}
	if firstUpsertIdx >= 0 && lastRetractIdx >= firstUpsertIdx {
		t.Fatalf("retraction call at index %d came after upsert at index %d", lastRetractIdx, firstUpsertIdx)
	}

	// Verify retraction uses repo_id and generation_id filters
	for i, call := range retractCalls {
		if !strings.Contains(call.Cypher, "DETACH DELETE") {
			t.Fatalf("retract call[%d] missing DETACH DELETE: %s", i, call.Cypher)
		}
		params := call.Parameters
		// All retraction calls should reference repo_id
		if _, ok := params["repo_id"]; !ok {
			// Some retractions use file_paths param instead
			if _, ok := params["file_paths"]; !ok {
				t.Fatalf("retract call[%d] missing repo_id or file_paths param", i)
			}
		}
	}
}

func TestCanonicalNodeWriterEmptyMaterialization(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	if len(exec.calls) != 0 {
		t.Fatalf("expected 0 executor calls for empty materialization, got %d", len(exec.calls))
	}
}

func TestCanonicalNodeWriterRepositoryOnly(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID:    "repo-1",
			Name:      "my-repo",
			Path:      "/repos/my-repo",
			LocalPath: "/repos/my-repo",
			RemoteURL: "https://github.com/org/my-repo",
			RepoSlug:  "org/my-repo",
			HasRemote: true,
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// Should have retraction calls + repository upsert even with no files/entities
	var repoUpsertFound bool
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert && strings.Contains(call.Cypher, "MERGE (r:Repository") {
			repoUpsertFound = true
			params := call.Parameters
			if params["repo_id"] != "repo-1" {
				t.Fatalf("repo_id = %v, want repo-1", params["repo_id"])
			}
			if params["name"] != "my-repo" {
				t.Fatalf("name = %v, want my-repo", params["name"])
			}
			if params["has_remote"] != true {
				t.Fatalf("has_remote = %v, want true", params["has_remote"])
			}
		}
	}
	if !repoUpsertFound {
		t.Fatal("expected repository upsert call")
	}
}

func TestCanonicalNodeWriterFilesCreateRepoContainsEdges(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-1",
			Name:   "my-repo",
			Path:   "/repos/my-repo",
		},
		Directories: []projector.DirectoryRow{
			{Path: "/repos/my-repo/src", Name: "src", ParentPath: "/repos/my-repo", RepoID: "repo-1", Depth: 0},
		},
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", Name: "main.go", Language: "go", RepoID: "repo-1", DirPath: "/repos/my-repo/src"},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// Find the file upsert call and verify it includes REPO_CONTAINS and CONTAINS edges
	var fileCypher string
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert && strings.Contains(call.Cypher, "MERGE (f:File") {
			fileCypher = call.Cypher
			break
		}
	}
	if fileCypher == "" {
		t.Fatal("expected file upsert call")
	}
	if !strings.Contains(fileCypher, "REPO_CONTAINS") {
		t.Fatalf("file cypher missing REPO_CONTAINS: %s", fileCypher)
	}
	if !strings.Contains(fileCypher, "MATCH (d:Directory") {
		t.Fatalf("file cypher missing Directory CONTAINS edge: %s", fileCypher)
	}
}

func TestCanonicalNodeWriterErrorPropagation(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{err: errors.New("neo4j connection failed")}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-1",
			Name:   "my-repo",
			Path:   "/repos/my-repo",
		},
	}

	err := writer.Write(context.Background(), mat)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "neo4j connection failed") {
		t.Fatalf("error = %v, want to contain 'neo4j connection failed'", err)
	}
}

func TestCanonicalNodeWriterDefaultBatchSize(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 0, nil) // 0 should default to DefaultBatchSize

	if writer.batchSize != DefaultBatchSize {
		t.Fatalf("batchSize = %d, want %d", writer.batchSize, DefaultBatchSize)
	}
}

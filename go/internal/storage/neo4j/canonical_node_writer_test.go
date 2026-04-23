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

type selectiveErrorExecutor struct {
	calls []Statement
	match func(Statement) bool
	err   error
}

func (m *selectiveErrorExecutor) Execute(_ context.Context, stmt Statement) error {
	m.calls = append(m.calls, stmt)
	if m.match != nil && m.match(stmt) {
		return m.err
	}
	return nil
}

// mockGroupExecutor implements both Executor and GroupExecutor for testing
// the atomic canonical write path.
type mockGroupExecutor struct {
	executeCalls []Statement // calls via Execute()
	groupCalls   int         // number of ExecuteGroup() invocations
	groupStmts   []Statement // statements from the last ExecuteGroup() call
	groupErr     error       // error to return from ExecuteGroup()
}

func (m *mockGroupExecutor) Execute(_ context.Context, stmt Statement) error {
	m.executeCalls = append(m.executeCalls, stmt)
	return nil
}

func (m *mockGroupExecutor) ExecuteGroup(_ context.Context, stmts []Statement) error {
	m.groupCalls++
	m.groupStmts = stmts
	return m.groupErr
}

type mockPhaseGroupExecutor struct {
	executeCalls    []Statement
	phaseGroupCalls int
	phaseGroups     [][]Statement
	phaseGroupErr   error
}

func (m *mockPhaseGroupExecutor) Execute(_ context.Context, stmt Statement) error {
	m.executeCalls = append(m.executeCalls, stmt)
	return nil
}

func (m *mockPhaseGroupExecutor) ExecutePhaseGroup(_ context.Context, stmts []Statement) error {
	m.phaseGroupCalls++
	cloned := append([]Statement(nil), stmts...)
	m.phaseGroups = append(m.phaseGroups, cloned)
	return m.phaseGroupErr
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
			} else if strings.Contains(call.Cypher, "MATCH (f:File {path: $file_path})") &&
				(strings.Contains(call.Cypher, "MATCH (n:Function {uid: $entity_id})") || strings.Contains(call.Cypher, "MATCH (n:Class {uid: $entity_id})")) {
				if len(phaseOrder) == 0 || phaseOrder[len(phaseOrder)-1] != "entity_containment" {
					phaseOrder = append(phaseOrder, "entity_containment")
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

	expected := []string{"retract", "repository", "directories", "files", "entities", "entity_containment", "modules", "structural_edges"}
	if len(phaseOrder) != len(expected) {
		t.Fatalf("phase order = %v, want %v", phaseOrder, expected)
	}
	for i := range expected {
		if phaseOrder[i] != expected[i] {
			t.Fatalf("phase[%d] = %q, want %q (full order: %v)", i, phaseOrder[i], expected[i], phaseOrder)
		}
	}
}

func TestCanonicalNodeWriterWriteReportsSequentialPhaseOnFailure(t *testing.T) {
	t.Parallel()

	exec := &selectiveErrorExecutor{
		match: func(stmt Statement) bool {
			return strings.Contains(stmt.Cypher, "IMPORTS")
		},
		err: errors.New("boom"),
	}
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
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", Name: "main.go", Language: "go", RepoID: "repo-1", DirPath: "/repos/my-repo/src"},
		},
		Imports: []projector.ImportRow{
			{FilePath: "/repos/my-repo/src/main.go", ModuleName: "fmt", ImportedName: "fmt", LineNumber: 3},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err == nil {
		t.Fatal("Write() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "canonical sequential write (structural_edges)") {
		t.Fatalf("Write() error = %q, want structural_edges phase context", err.Error())
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

func TestCanonicalNodeWriterEntityUpsertsRemainLabelScoped(t *testing.T) {
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

	if len(entityCalls) != 3 {
		t.Fatalf("expected 3 entity upserts (2 Function, 1 Class), got %d", len(entityCalls))
	}

	var functionCount, classCount int
	for _, call := range entityCalls {
		if strings.Contains(call.Cypher, "MERGE (n:Function") {
			functionCount++
			if got := call.Parameters["entity_id"]; got != "f1" && got != "f2" {
				t.Fatalf("function entity_id = %#v, want f1 or f2", got)
			}
			if _, ok := call.Parameters["properties"].(map[string]any); !ok {
				t.Fatalf("function properties type = %T, want map[string]any", call.Parameters["properties"])
			}
			continue
		}
		if strings.Contains(call.Cypher, "MERGE (n:Class") {
			classCount++
			if got, want := call.Parameters["entity_id"], "c1"; got != want {
				t.Fatalf("class entity_id = %#v, want %#v", got, want)
			}
			if _, ok := call.Parameters["properties"].(map[string]any); !ok {
				t.Fatalf("class properties type = %T, want map[string]any", call.Parameters["properties"])
			}
			continue
		}
		t.Fatalf("unexpected entity cypher: %s", call.Cypher)
	}
	if got, want := functionCount, 2; got != want {
		t.Fatalf("function upsert count = %d, want %d", got, want)
	}
	if got, want := classCount, 1; got != want {
		t.Fatalf("class upsert count = %d, want %d", got, want)
	}
}

func TestCanonicalNodeWriterProjectsTypeScriptClassFamilyMetadata(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-ts-1",
		GenerationID: "gen-ts-1",
		RepoID:       "repo-ts-1",
		RepoPath:     "/repos/ts",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-ts-1",
			Name:   "ts-repo",
			Path:   "/repos/ts",
		},
		Entities: []projector.EntityRow{
			{
				EntityID:     "class-1",
				Label:        "Class",
				EntityName:   "Service",
				FilePath:     "/repos/ts/src/service.ts",
				RelativePath: "src/service.ts",
				StartLine:    3,
				EndLine:      18,
				Language:     "typescript",
				RepoID:       "repo-ts-1",
				Metadata: map[string]any{
					"decorators":              []any{"@sealed"},
					"type_parameters":         []any{"T"},
					"declaration_merge_group": "Service",
					"declaration_merge_count": 2,
					"declaration_merge_kinds": []any{"class", "namespace"},
				},
			},
			{
				EntityID:     "interface-1",
				Label:        "Interface",
				EntityName:   "Service",
				FilePath:     "/repos/ts/src/service.ts",
				RelativePath: "src/service.ts",
				StartLine:    20,
				EndLine:      32,
				Language:     "typescript",
				RepoID:       "repo-ts-1",
				Metadata: map[string]any{
					"declaration_merge_group": "Service",
					"declaration_merge_count": 2,
					"declaration_merge_kinds": []any{"class", "interface"},
				},
			},
			{
				EntityID:     "enum-1",
				Label:        "Enum",
				EntityName:   "ServiceKind",
				FilePath:     "/repos/ts/src/service.ts",
				RelativePath: "src/service.ts",
				StartLine:    34,
				EndLine:      42,
				Language:     "typescript",
				RepoID:       "repo-ts-1",
				Metadata: map[string]any{
					"declaration_merge_group": "ServiceKind",
					"declaration_merge_count": 2,
					"declaration_merge_kinds": []any{"enum", "namespace"},
				},
			},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	var entityCalls []Statement
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert &&
			(strings.Contains(call.Cypher, "MERGE (n:Class") ||
				strings.Contains(call.Cypher, "MERGE (n:Interface") ||
				strings.Contains(call.Cypher, "MERGE (n:Enum")) {
			entityCalls = append(entityCalls, call)
		}
	}
	if len(entityCalls) != 3 {
		t.Fatalf("expected 3 TS class-family entity upserts, got %d", len(entityCalls))
	}

	for _, call := range entityCalls {
		if !strings.Contains(call.Cypher, "SET n += $properties") {
			t.Fatalf("TS class-family cypher missing map property merge: %s", call.Cypher)
		}
	}

	var classProperties map[string]any
	for _, call := range entityCalls {
		if strings.Contains(call.Cypher, "MERGE (n:Class") {
			props, ok := call.Parameters["properties"].(map[string]any)
			if !ok {
				t.Fatalf("class properties type = %T, want map[string]any", call.Parameters["properties"])
			}
			classProperties = props
			break
		}
	}
	if len(classProperties) == 0 {
		t.Fatal("missing Class properties in TS class-family entity calls")
	}
	decorators, ok := classProperties["decorators"].([]string)
	if !ok {
		t.Fatalf("class properties[decorators] type = %T, want []string", classProperties["decorators"])
	}
	if got, want := len(decorators), 1; got != want || decorators[0] != "@sealed" {
		t.Fatalf("class properties[decorators] = %#v, want [@sealed]", decorators)
	}
	typeParameters, ok := classProperties["type_parameters"].([]string)
	if !ok {
		t.Fatalf("class properties[type_parameters] type = %T, want []string", classProperties["type_parameters"])
	}
	if got, want := len(typeParameters), 1; got != want || typeParameters[0] != "T" {
		t.Fatalf("class properties[type_parameters] = %#v, want [T]", typeParameters)
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

func TestCanonicalNodeWriterDirectoryGenerationID(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-dir",
		GenerationID: "gen-dir",
		RepoID:       "repo-dir",
		RepoPath:     "/repos/dir-repo",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-dir",
			Name:   "dir-repo",
			Path:   "/repos/dir-repo",
		},
		Directories: []projector.DirectoryRow{
			{Path: "/repos/dir-repo/src", Name: "src", ParentPath: "/repos/dir-repo", RepoID: "repo-dir", Depth: 0},
			{Path: "/repos/dir-repo/src/pkg", Name: "pkg", ParentPath: "/repos/dir-repo/src", RepoID: "repo-dir", Depth: 1},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// Verify directory row maps include generation_id and scope_id
	for _, call := range exec.calls {
		if call.Operation != OperationCanonicalUpsert || !strings.Contains(call.Cypher, "MERGE (d:Directory") {
			continue
		}
		rows, ok := call.Parameters["rows"].([]map[string]any)
		if !ok {
			t.Fatal("directory upsert missing rows parameter")
		}
		for i, row := range rows {
			if row["generation_id"] != "gen-dir" {
				t.Fatalf("directory row[%d] generation_id = %v, want gen-dir", i, row["generation_id"])
			}
			if row["scope_id"] != "scope-dir" {
				t.Fatalf("directory row[%d] scope_id = %v, want scope-dir", i, row["scope_id"])
			}
		}
	}

	// Verify directory MERGE Cypher sets generation_id
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert && strings.Contains(call.Cypher, "MERGE (d:Directory") {
			if !strings.Contains(call.Cypher, "d.generation_id") {
				t.Fatalf("directory MERGE Cypher missing generation_id: %s", call.Cypher)
			}
			if !strings.Contains(call.Cypher, "d.scope_id") {
				t.Fatalf("directory MERGE Cypher missing scope_id: %s", call.Cypher)
			}
		}
	}

	// Verify directory retract Cypher includes generation_id filter
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalRetract && strings.Contains(call.Cypher, "Directory") {
			if !strings.Contains(call.Cypher, "generation_id") {
				t.Fatalf("directory retract Cypher missing generation_id filter: %s", call.Cypher)
			}
		}
	}
}

func TestCanonicalNodeWriterAtomicGroupExecutor(t *testing.T) {
	t.Parallel()

	exec := &mockGroupExecutor{}
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
		Entities: []projector.EntityRow{
			{EntityID: "e1", Label: "Function", EntityName: "main", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 5, EndLine: 10, Language: "go", RepoID: "repo-1"},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// When GroupExecutor is available, ALL statements go through a single ExecuteGroup call
	if exec.groupCalls != 1 {
		t.Fatalf("ExecuteGroup calls = %d, want 1", exec.groupCalls)
	}
	if len(exec.executeCalls) != 0 {
		t.Fatalf("Execute calls = %d, want 0 (should use atomic path)", len(exec.executeCalls))
	}

	// Verify statements include all phases in order: retract, repository, directories, files, entities
	stmts := exec.groupStmts
	if len(stmts) == 0 {
		t.Fatal("expected grouped statements, got 0")
	}

	// First statements should be retractions
	if stmts[0].Operation != OperationCanonicalRetract {
		t.Fatalf("first statement operation = %q, want %q", stmts[0].Operation, OperationCanonicalRetract)
	}

	// Last statements should be upserts
	last := stmts[len(stmts)-1]
	if last.Operation != OperationCanonicalUpsert {
		t.Fatalf("last statement operation = %q, want %q", last.Operation, OperationCanonicalUpsert)
	}

	// Verify phase ordering within the group: retracts before upserts
	lastRetractIdx := -1
	firstUpsertIdx := -1
	for i, stmt := range stmts {
		if stmt.Operation == OperationCanonicalRetract {
			lastRetractIdx = i
		}
		if stmt.Operation == OperationCanonicalUpsert && firstUpsertIdx == -1 {
			firstUpsertIdx = i
		}
	}
	if firstUpsertIdx >= 0 && lastRetractIdx >= firstUpsertIdx {
		t.Fatalf("retraction at index %d came after upsert at index %d", lastRetractIdx, firstUpsertIdx)
	}
}

func TestCanonicalNodeWriterFallsBackToSequential(t *testing.T) {
	t.Parallel()

	// mockExecutor only implements Executor, NOT GroupExecutor
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
			{Path: "/f1.go", RelativePath: "f1.go", Name: "f1.go", Language: "go", RepoID: "repo-1", DirPath: "/src"},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	// Sequential path: all calls go through Execute()
	if len(exec.calls) == 0 {
		t.Fatal("expected Execute() calls for sequential fallback, got 0")
	}
}

func TestCanonicalNodeWriterUsesPhaseGroupExecutor(t *testing.T) {
	t.Parallel()

	exec := &mockPhaseGroupExecutor{}
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
			{Path: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", Name: "main.go", Language: "go", RepoID: "repo-1", DirPath: "/repos/my-repo/src"},
		},
		Entities: []projector.EntityRow{
			{EntityID: "e1", Label: "Function", EntityName: "main", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 5, EndLine: 10, Language: "go", RepoID: "repo-1"},
		},
	}

	if err := writer.Write(context.Background(), mat); err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	if got := len(exec.executeCalls); got != 0 {
		t.Fatalf("Execute calls = %d, want 0 for phase-group path", got)
	}
	if got := exec.phaseGroupCalls; got == 0 {
		t.Fatal("phaseGroupCalls = 0, want at least one phase group")
	}
	if got := len(exec.phaseGroups); got < 4 {
		t.Fatalf("phase group count = %d, want multiple ordered phases", got)
	}
	if got, want := exec.phaseGroups[0][0].Operation, OperationCanonicalRetract; got != want {
		t.Fatalf("first phase first operation = %q, want %q", got, want)
	}
}

func TestCanonicalNodeWriterAtomicGroupExecutorError(t *testing.T) {
	t.Parallel()

	exec := &mockGroupExecutor{groupErr: errors.New("neo4j transaction too large")}
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
	if !strings.Contains(err.Error(), "neo4j transaction too large") {
		t.Fatalf("error = %v, want to contain 'neo4j transaction too large'", err)
	}
}

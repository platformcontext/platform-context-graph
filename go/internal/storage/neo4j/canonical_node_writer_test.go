package neo4j

import (
	"context"
	"errors"
	"sort"
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

	// Verify strict phase order: retract phases first, then repository, directories, files, entities, entity containment, modules, structural edges.
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
			} else if call.Parameters[StatementMetadataPhaseKey] == CanonicalPhaseEntityContainment {
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
			return stmt.Operation == OperationCanonicalUpsert && strings.Contains(stmt.Cypher, "IMPORTS")
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

	// Collect batched entity-phase calls
	var entityCalls []Statement
	for _, call := range exec.calls {
		if call.Operation == OperationCanonicalUpsert &&
			(strings.Contains(call.Cypher, "MERGE (n:Function") || strings.Contains(call.Cypher, "MERGE (n:Class")) {
			entityCalls = append(entityCalls, call)
		}
	}

	if len(entityCalls) != 2 {
		t.Fatalf("expected 2 entity batches (Function + Class), got %d", len(entityCalls))
	}

	var functionCount, classCount int
	for _, call := range entityCalls {
		rows, ok := call.Parameters["rows"].([]map[string]any)
		if !ok {
			t.Fatalf("rows type = %T, want []map[string]any", call.Parameters["rows"])
		}
		if strings.Contains(call.Cypher, "MERGE (n:Function") {
			functionCount += len(rows)
			if got, want := len(rows), 2; got != want {
				t.Fatalf("function batch size = %d, want %d", got, want)
			}
			continue
		}
		if strings.Contains(call.Cypher, "MERGE (n:Class") {
			classCount += len(rows)
			if got, want := len(rows), 1; got != want {
				t.Fatalf("class batch size = %d, want %d", got, want)
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
		if !strings.Contains(call.Cypher, "SET n += row.props") {
			t.Fatalf("TS class-family cypher missing row.props merge: %s", call.Cypher)
		}
	}

	var classProperties map[string]any
	for _, call := range entityCalls {
		if strings.Contains(call.Cypher, "MERGE (n:Class") {
			rows, ok := call.Parameters["rows"].([]map[string]any)
			if !ok {
				t.Fatalf("class rows type = %T, want []map[string]any", call.Parameters["rows"])
			}
			if got, want := len(rows), 1; got != want {
				t.Fatalf("class row count = %d, want %d", got, want)
			}
			props, ok := rows[0]["props"].(map[string]any)
			if !ok {
				t.Fatalf("class props type = %T, want map[string]any", rows[0]["props"])
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

func TestCanonicalNodeWriterProjectsInfrastructureIdentityMetadata(t *testing.T) {
	t.Parallel()

	exec := &mockExecutor{}
	writer := NewCanonicalNodeWriter(exec, 500, nil)

	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-infra-1",
		GenerationID: "gen-infra-1",
		RepoID:       "repo-infra-1",
		RepoPath:     "/repos/infra",
		Repository: &projector.RepositoryRow{
			RepoID: "repo-infra-1",
			Name:   "infra-repo",
			Path:   "/repos/infra",
		},
		Entities: []projector.EntityRow{
			{
				EntityID:     "claim-1",
				Label:        "CrossplaneClaim",
				EntityName:   "database",
				FilePath:     "/repos/infra/control-plane/claim.yaml",
				RelativePath: "control-plane/claim.yaml",
				StartLine:    7,
				EndLine:      20,
				Language:     "yaml",
				RepoID:       "repo-infra-1",
				Metadata: map[string]any{
					"kind":        "SQLInstance",
					"api_version": "database.example.org/v1alpha1",
					"namespace":   "platform",
				},
			},
			{
				EntityID:     "deployment-1",
				Label:        "K8sResource",
				EntityName:   "api",
				FilePath:     "/repos/infra/deploy/deployment.yaml",
				RelativePath: "deploy/deployment.yaml",
				StartLine:    3,
				EndLine:      40,
				Language:     "yaml",
				RepoID:       "repo-infra-1",
				Metadata: map[string]any{
					"kind":           "Deployment",
					"api_version":    "apps/v1",
					"namespace":      "prod",
					"qualified_name": "prod/Deployment/api",
				},
			},
		},
	}

	err := writer.Write(context.Background(), mat)
	if err != nil {
		t.Fatalf("Write() error = %v", err)
	}

	propsByLabel := map[string]map[string]any{}
	for _, call := range exec.calls {
		if call.Operation != OperationCanonicalUpsert {
			continue
		}
		for _, label := range []string{"CrossplaneClaim", "K8sResource"} {
			if !strings.Contains(call.Cypher, "MERGE (n:"+label) {
				continue
			}
			rows, ok := call.Parameters["rows"].([]map[string]any)
			if !ok {
				t.Fatalf("%s rows type = %T, want []map[string]any", label, call.Parameters["rows"])
			}
			if got, want := len(rows), 1; got != want {
				t.Fatalf("%s row count = %d, want %d", label, got, want)
			}
			props, ok := rows[0]["props"].(map[string]any)
			if !ok {
				t.Fatalf("%s props type = %T, want map[string]any", label, rows[0]["props"])
			}
			propsByLabel[label] = props
		}
	}

	claimProps := propsByLabel["CrossplaneClaim"]
	if len(claimProps) == 0 {
		t.Fatal("missing CrossplaneClaim properties")
	}
	if got, want := claimProps["kind"], "SQLInstance"; got != want {
		t.Fatalf("CrossplaneClaim kind = %#v, want %#v", got, want)
	}
	if got, want := claimProps["api_version"], "database.example.org/v1alpha1"; got != want {
		t.Fatalf("CrossplaneClaim api_version = %#v, want %#v", got, want)
	}
	if got, want := claimProps["namespace"], "platform"; got != want {
		t.Fatalf("CrossplaneClaim namespace = %#v, want %#v", got, want)
	}

	resourceProps := propsByLabel["K8sResource"]
	if len(resourceProps) == 0 {
		t.Fatal("missing K8sResource properties")
	}
	if got, want := resourceProps["kind"], "Deployment"; got != want {
		t.Fatalf("K8sResource kind = %#v, want %#v", got, want)
	}
	if got, want := resourceProps["qualified_name"], "prod/Deployment/api"; got != want {
		t.Fatalf("K8sResource qualified_name = %#v, want %#v", got, want)
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

	// Verify retraction deletes stale nodes or refreshes current structural
	// edges and carries the identity parameters needed for its scope.
	for i, call := range retractCalls {
		if !strings.Contains(call.Cypher, "DELETE") {
			t.Fatalf("retract call[%d] missing DELETE: %s", i, call.Cypher)
		}
		params := call.Parameters
		if _, ok := params["repo_id"]; !ok {
			if _, ok := params["file_paths"]; !ok {
				if _, ok := params["entity_ids"]; !ok {
					t.Fatalf("retract call[%d] missing repo_id, file_paths, or entity_ids param", i)
				}
			}
		}
	}
}

func TestCanonicalNodeWriterFileRetractPreservesCurrentFilePaths(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	mat := projector.CanonicalMaterialization{
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/main.go"},
			{Path: "/repos/my-repo/internal/graph.go"},
		},
	}

	var fileRetract Statement
	for _, stmt := range writer.buildRetractStatements(mat) {
		if stmt.Operation == OperationCanonicalRetract && strings.Contains(stmt.Cypher, "MATCH (f:File)") {
			fileRetract = stmt
			break
		}
	}
	if fileRetract.Cypher == "" {
		t.Fatal("missing File retract statement")
	}
	if !strings.Contains(fileRetract.Cypher, "NOT (f.path IN $file_paths)") {
		t.Fatalf("File retract cypher = %q, want current path exclusion", fileRetract.Cypher)
	}

	gotPaths, ok := fileRetract.Parameters["file_paths"].([]string)
	if !ok {
		t.Fatalf("file_paths parameter type = %T, want []string", fileRetract.Parameters["file_paths"])
	}
	wantPaths := []string{"/repos/my-repo/main.go", "/repos/my-repo/internal/graph.go"}
	if strings.Join(gotPaths, "\n") != strings.Join(wantPaths, "\n") {
		t.Fatalf("file_paths = %v, want %v", gotPaths, wantPaths)
	}
}

func TestCanonicalNodeWriterRetractPreservesCurrentEntityAndDirectoryIdentities(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	mat := projector.CanonicalMaterialization{
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		Directories: []projector.DirectoryRow{
			{Path: "/repos/my-repo/internal"},
			{Path: "/repos/my-repo/cmd"},
		},
		Entities: []projector.EntityRow{
			{EntityID: "entity-function-1", Label: "Function"},
			{EntityID: "entity-struct-1", Label: "Struct"},
			{EntityID: "entity-k8s-1", Label: "K8sResource"},
		},
	}

	var codeRetract Statement
	var infraRetract Statement
	var directoryRetract Statement
	for _, stmt := range writer.buildRetractStatements(mat) {
		switch {
		case strings.Contains(stmt.Cypher, "n:Function OR n:Class"):
			codeRetract = stmt
		case strings.Contains(stmt.Cypher, "n:K8sResource OR n:ArgoCDApplication"):
			infraRetract = stmt
		case strings.Contains(stmt.Cypher, "MATCH (d:Directory)"):
			directoryRetract = stmt
		}
	}
	if codeRetract.Cypher == "" {
		t.Fatal("missing code entity retract statement")
	}
	if !strings.Contains(codeRetract.Cypher, "NOT (n.uid IN $entity_ids)") {
		t.Fatalf("code entity retract cypher = %q, want current entity exclusion", codeRetract.Cypher)
	}
	gotEntityIDs, ok := codeRetract.Parameters["entity_ids"].([]string)
	if !ok {
		t.Fatalf("entity_ids parameter type = %T, want []string", codeRetract.Parameters["entity_ids"])
	}
	wantEntityIDs := []string{"entity-function-1", "entity-struct-1"}
	if strings.Join(gotEntityIDs, "\n") != strings.Join(wantEntityIDs, "\n") {
		t.Fatalf("entity_ids = %v, want %v", gotEntityIDs, wantEntityIDs)
	}
	if infraRetract.Cypher == "" {
		t.Fatal("missing infra entity retract statement")
	}
	gotInfraEntityIDs, ok := infraRetract.Parameters["entity_ids"].([]string)
	if !ok {
		t.Fatalf("infra entity_ids parameter type = %T, want []string", infraRetract.Parameters["entity_ids"])
	}
	if strings.Join(gotInfraEntityIDs, "\n") != "entity-k8s-1" {
		t.Fatalf("infra entity_ids = %v, want [entity-k8s-1]", gotInfraEntityIDs)
	}

	if directoryRetract.Cypher == "" {
		t.Fatal("missing Directory retract statement")
	}
	if !strings.Contains(directoryRetract.Cypher, "NOT (d.path IN $directory_paths)") {
		t.Fatalf("Directory retract cypher = %q, want current path exclusion", directoryRetract.Cypher)
	}
	gotDirectoryPaths, ok := directoryRetract.Parameters["directory_paths"].([]string)
	if !ok {
		t.Fatalf("directory_paths parameter type = %T, want []string", directoryRetract.Parameters["directory_paths"])
	}
	wantDirectoryPaths := []string{"/repos/my-repo/internal", "/repos/my-repo/cmd"}
	if strings.Join(gotDirectoryPaths, "\n") != strings.Join(wantDirectoryPaths, "\n") {
		t.Fatalf("directory_paths = %v, want %v", gotDirectoryPaths, wantDirectoryPaths)
	}
}

func TestCanonicalNodeWriterRetractLeavesRemovedIdentitiesEligibleForDeletion(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	mat := projector.CanonicalMaterialization{
		GenerationID: "gen-2",
		RepoID:       "repo-1",
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/readded.go"},
		},
		Directories: []projector.DirectoryRow{
			{Path: "/repos/my-repo"},
		},
		Entities: []projector.EntityRow{
			{EntityID: "content-entity:readded", Label: "Function"},
		},
	}

	var fileRetract Statement
	var codeRetract Statement
	var directoryRetract Statement
	for _, stmt := range writer.buildRetractStatements(mat) {
		switch {
		case strings.Contains(stmt.Cypher, "MATCH (f:File)"):
			fileRetract = stmt
		case strings.Contains(stmt.Cypher, "n:Function OR n:Class"):
			codeRetract = stmt
		case strings.Contains(stmt.Cypher, "MATCH (d:Directory)"):
			directoryRetract = stmt
		}
	}

	for _, tt := range []struct {
		name      string
		stmt      Statement
		paramName string
		current   string
		removed   string
	}{
		{name: "file", stmt: fileRetract, paramName: "file_paths", current: "/repos/my-repo/readded.go", removed: "/repos/my-repo/deleted.go"},
		{name: "code entity", stmt: codeRetract, paramName: "entity_ids", current: "content-entity:readded", removed: "content-entity:deleted"},
		{name: "directory", stmt: directoryRetract, paramName: "directory_paths", current: "/repos/my-repo", removed: "/repos/old"},
	} {
		values, ok := tt.stmt.Parameters[tt.paramName].([]string)
		if !ok {
			t.Fatalf("%s %s parameter type = %T, want []string", tt.name, tt.paramName, tt.stmt.Parameters[tt.paramName])
		}
		if !stringSliceContains(values, tt.current) {
			t.Fatalf("%s %s = %v, want current identity %q preserved", tt.name, tt.paramName, values, tt.current)
		}
		if stringSliceContains(values, tt.removed) {
			t.Fatalf("%s %s = %v, removed identity %q should remain retractable", tt.name, tt.paramName, values, tt.removed)
		}
	}
}

func TestCanonicalNodeWriterRetractRefreshesCurrentStructuralEdges(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	mat := projector.CanonicalMaterialization{
		GenerationID: "gen-2",
		RepoID:       "repo-1",
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/main.go"},
		},
		Entities: []projector.EntityRow{
			{EntityID: "content-entity:function", Label: "Function"},
		},
	}

	var importRefresh Statement
	var directoryFileRefresh Statement
	var fileEntityRefresh Statement
	var entityContainmentRefresh Statement
	for _, stmt := range writer.buildRetractStatements(mat) {
		switch {
		case strings.Contains(stmt.Cypher, "-[r:IMPORTS]->"):
			importRefresh = stmt
		case strings.Contains(stmt.Cypher, "]->(f:File)"):
			directoryFileRefresh = stmt
		case strings.Contains(stmt.Cypher, "(f:File)-[r:CONTAINS]->(n)"):
			fileEntityRefresh = stmt
		case strings.Contains(stmt.Cypher, "(n)-[r:CONTAINS]->(m)"):
			entityContainmentRefresh = stmt
		}
	}

	for _, tt := range []struct {
		name      string
		stmt      Statement
		paramName string
		want      string
	}{
		{name: "imports", stmt: importRefresh, paramName: "file_paths", want: "/repos/my-repo/main.go"},
		{name: "directory file contains", stmt: directoryFileRefresh, paramName: "file_paths", want: "/repos/my-repo/main.go"},
		{name: "file entity contains", stmt: fileEntityRefresh, paramName: "file_paths", want: "/repos/my-repo/main.go"},
		{name: "entity contains", stmt: entityContainmentRefresh, paramName: "entity_ids", want: "content-entity:function"},
	} {
		if tt.stmt.Cypher == "" {
			t.Fatalf("missing %s refresh statement", tt.name)
		}
		values, ok := tt.stmt.Parameters[tt.paramName].([]string)
		if !ok {
			t.Fatalf("%s %s parameter type = %T, want []string", tt.name, tt.paramName, tt.stmt.Parameters[tt.paramName])
		}
		if !stringSliceContains(values, tt.want) {
			t.Fatalf("%s %s = %v, want %q", tt.name, tt.paramName, values, tt.want)
		}
	}
}

func TestCanonicalNodeWriterRefreshesStructuralEdgesBeforeEntityRetract(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	mat := projector.CanonicalMaterialization{
		GenerationID: "gen-2",
		RepoID:       "repo-1",
		Files: []projector.FileRow{
			{Path: "/repos/my-repo/main.go"},
		},
		Entities: []projector.EntityRow{
			{EntityID: "content-entity:function", Label: "Function"},
		},
	}

	fileEntityRefreshIdx := -1
	codeEntityRetractIdx := -1
	for i, stmt := range writer.buildRetractStatements(mat) {
		switch {
		case strings.Contains(stmt.Cypher, "(f:File)-[r:CONTAINS]->(n)"):
			fileEntityRefreshIdx = i
		case strings.Contains(stmt.Cypher, "n:Function OR n:Class"):
			codeEntityRetractIdx = i
		}
	}

	if fileEntityRefreshIdx < 0 {
		t.Fatal("missing file/entity refresh statement")
	}
	if codeEntityRetractIdx < 0 {
		t.Fatal("missing code entity retract statement")
	}
	if fileEntityRefreshIdx > codeEntityRetractIdx {
		t.Fatalf("file/entity refresh index = %d, code entity retract index = %d; refresh must run first",
			fileEntityRefreshIdx, codeEntityRetractIdx)
	}
}

func TestCanonicalNodeWriterBatchesCurrentFileStructuralEdgeRefresh(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	files := make([]projector.FileRow, canonicalNodeRefreshFileEntityPathBatchSize+1)
	for i := range files {
		files[i] = projector.FileRow{Path: "/repos/my-repo/file-" + string(rune('a'+i%26))}
	}
	mat := projector.CanonicalMaterialization{
		GenerationID: "gen-2",
		RepoID:       "repo-1",
		Files:        files,
	}

	var fileEntityRefreshes []Statement
	for _, stmt := range writer.buildRetractStatements(mat) {
		if strings.Contains(stmt.Cypher, "(f:File)-[r:CONTAINS]->(n)") {
			fileEntityRefreshes = append(fileEntityRefreshes, stmt)
		}
	}
	if got, want := len(fileEntityRefreshes), 2; got != want {
		t.Fatalf("file/entity refresh statement count = %d, want %d", got, want)
	}
	for i, stmt := range fileEntityRefreshes {
		paths, ok := stmt.Parameters["file_paths"].([]string)
		if !ok {
			t.Fatalf("refresh[%d] file_paths type = %T, want []string", i, stmt.Parameters["file_paths"])
		}
		if len(paths) > canonicalNodeRefreshFileEntityPathBatchSize {
			t.Fatalf("refresh[%d] file_paths len = %d, want <= %d",
				i, len(paths), canonicalNodeRefreshFileEntityPathBatchSize)
		}
	}
}

func TestCanonicalNodeWriterRetractCoversProjectableEntityLabels(t *testing.T) {
	t.Parallel()

	covered := make(map[string]string)
	for _, family := range []struct {
		name   string
		labels map[string]struct{}
		cypher string
	}{
		{name: "code", labels: canonicalNodeRetractCodeEntityLabels, cypher: canonicalNodeRetractCodeEntitiesCypher},
		{name: "infra", labels: canonicalNodeRetractInfraEntityLabels, cypher: canonicalNodeRetractInfraEntitiesCypher},
		{name: "terraform", labels: canonicalNodeRetractTerraformEntityLabels, cypher: canonicalNodeRetractTerraformEntitiesCypher},
		{name: "cloudformation", labels: canonicalNodeRetractCloudFormationEntityLabels, cypher: canonicalNodeRetractCloudFormationEntitiesCypher},
		{name: "sql", labels: canonicalNodeRetractSQLEntityLabels, cypher: canonicalNodeRetractSQLEntitiesCypher},
		{name: "data", labels: canonicalNodeRetractDataEntityLabels, cypher: canonicalNodeRetractDataEntitiesCypher},
	} {
		for label := range family.labels {
			if previous, exists := covered[label]; exists {
				t.Fatalf("label %s covered by both %s and %s retract families", label, previous, family.name)
			}
			covered[label] = family.name
			if !strings.Contains(family.cypher, "n:"+label) {
				t.Fatalf("%s label set includes %s but cypher does not", family.name, label)
			}
		}
	}

	var missing []string
	for _, label := range projector.EntityTypeLabelMap() {
		if label == "Module" || label == "Parameter" {
			continue
		}
		if _, ok := covered[label]; !ok {
			missing = append(missing, label)
		}
	}
	if len(missing) > 0 {
		sort.Strings(missing)
		t.Fatalf("retract families missing projectable labels: %s", strings.Join(missing, ", "))
	}
}

func stringSliceContains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
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

func TestCanonicalNodeWriterEntityStatementsIncludePhaseDiagnostics(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Entities: []projector.EntityRow{
			{
				EntityID:     "e1",
				Label:        "Function",
				EntityName:   "main",
				FilePath:     "/repos/my-repo/src/main.go",
				RelativePath: "src/main.go",
				StartLine:    5,
				EndLine:      10,
				Language:     "go",
				RepoID:       "repo-1",
			},
		},
	}

	stmts := writer.buildEntityStatements(mat)
	if len(stmts) == 0 {
		t.Fatal("buildEntityStatements() returned no statements")
	}
	for _, stmt := range stmts {
		if got, want := stmt.Parameters["_pcg_phase"], "entities"; got != want {
			t.Fatalf("entity statement _pcg_phase = %#v, want %#v", got, want)
		}
	}
}

func TestCanonicalNodeWriterSingletonFallbackMarksExecuteOnlyMode(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil)
	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Entities: []projector.EntityRow{
			{
				EntityID:     "e-shortest",
				Label:        "Function",
				EntityName:   "TestHandleCallChainReturnsShortestPath",
				FilePath:     "/repos/my-repo/src/main.go",
				RelativePath: "src/main.go",
				StartLine:    5,
				EndLine:      10,
				Language:     "go",
				RepoID:       "repo-1",
			},
		},
	}

	stmts := writer.buildEntityStatements(mat)
	if len(stmts) != 1 {
		t.Fatalf("buildEntityStatements() count = %d, want 1", len(stmts))
	}
	if got, want := stmts[0].Parameters["_pcg_phase_group_mode"], "execute_only"; got != want {
		t.Fatalf("singleton fallback _pcg_phase_group_mode = %#v, want %#v", got, want)
	}
}

func TestCanonicalNodeWriterEntityBatchSizeOverride(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil).WithEntityBatchSize(2)
	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Entities: []projector.EntityRow{
			{EntityID: "e1", Label: "Function", EntityName: "one", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 1, EndLine: 2, Language: "go", RepoID: "repo-1"},
			{EntityID: "e2", Label: "Function", EntityName: "two", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 3, EndLine: 4, Language: "go", RepoID: "repo-1"},
			{EntityID: "e3", Label: "Function", EntityName: "three", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 5, EndLine: 6, Language: "go", RepoID: "repo-1"},
		},
	}

	stmts := writer.buildEntityStatements(mat)
	if got, want := len(stmts), 2; got != want {
		t.Fatalf("buildEntityStatements() count = %d, want %d", got, want)
	}
	firstRows, _ := stmts[0].Parameters["rows"].([]map[string]any)
	secondRows, _ := stmts[1].Parameters["rows"].([]map[string]any)
	if got, want := len(firstRows), 2; got != want {
		t.Fatalf("first entity batch rows = %d, want %d", got, want)
	}
	if got, want := len(secondRows), 1; got != want {
		t.Fatalf("second entity batch rows = %d, want %d", got, want)
	}
}

func TestCanonicalNodeWriterEntityLabelBatchSizeOverride(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil).
		WithEntityBatchSize(100).
		WithEntityLabelBatchSize("Function", 2)
	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Entities: []projector.EntityRow{
			{EntityID: "c1", Label: "Class", EntityName: "One", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 1, EndLine: 2, Language: "go", RepoID: "repo-1"},
			{EntityID: "c2", Label: "Class", EntityName: "Two", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 3, EndLine: 4, Language: "go", RepoID: "repo-1"},
			{EntityID: "f1", Label: "Function", EntityName: "one", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 5, EndLine: 6, Language: "go", RepoID: "repo-1"},
			{EntityID: "f2", Label: "Function", EntityName: "two", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 7, EndLine: 8, Language: "go", RepoID: "repo-1"},
			{EntityID: "f3", Label: "Function", EntityName: "three", FilePath: "/repos/my-repo/src/main.go", RelativePath: "src/main.go", StartLine: 9, EndLine: 10, Language: "go", RepoID: "repo-1"},
		},
	}

	stmts := writer.buildEntityStatements(mat)
	if got, want := len(stmts), 3; got != want {
		t.Fatalf("buildEntityStatements() count = %d, want %d", got, want)
	}

	var classRows []int
	var functionRows []int
	for _, stmt := range stmts {
		rows, _ := stmt.Parameters["rows"].([]map[string]any)
		summary, _ := stmt.Parameters["_pcg_statement_summary"].(string)
		switch {
		case strings.Contains(summary, "label=Class"):
			classRows = append(classRows, len(rows))
		case strings.Contains(summary, "label=Function"):
			functionRows = append(functionRows, len(rows))
		}
	}

	if got, want := len(classRows), 1; got != want {
		t.Fatalf("class batch count = %d, want %d", got, want)
	}
	if got, want := classRows[0], 2; got != want {
		t.Fatalf("class batch rows = %d, want %d", got, want)
	}
	if got, want := stmts[0].Parameters[StatementMetadataEntityLabelKey], "Class"; got != want {
		t.Fatalf("class statement entity label = %#v, want %#v", got, want)
	}
	if got, want := stmts[1].Parameters[StatementMetadataEntityLabelKey], "Function"; got != want {
		t.Fatalf("function statement entity label = %#v, want %#v", got, want)
	}
	if got, want := len(functionRows), 2; got != want {
		t.Fatalf("function batch count = %d, want %d", got, want)
	}
	if got, want := functionRows[0], 2; got != want {
		t.Fatalf("first function batch rows = %d, want %d", got, want)
	}
	if got, want := functionRows[1], 1; got != want {
		t.Fatalf("second function batch rows = %d, want %d", got, want)
	}
}

func TestCanonicalNodeWriterEntityBatchesCrossFileBoundaries(t *testing.T) {
	t.Parallel()

	writer := NewCanonicalNodeWriter(&mockExecutor{}, 500, nil).WithEntityBatchSize(10)
	mat := projector.CanonicalMaterialization{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		RepoID:       "repo-1",
		RepoPath:     "/repos/my-repo",
		Entities: []projector.EntityRow{
			{EntityID: "f1", Label: "Function", EntityName: "one", FilePath: "/repos/my-repo/src/a.go", RelativePath: "src/a.go", StartLine: 1, EndLine: 2, Language: "go", RepoID: "repo-1"},
			{EntityID: "f2", Label: "Function", EntityName: "two", FilePath: "/repos/my-repo/src/b.go", RelativePath: "src/b.go", StartLine: 3, EndLine: 4, Language: "go", RepoID: "repo-1"},
			{EntityID: "f3", Label: "Function", EntityName: "three", FilePath: "/repos/my-repo/src/a.go", RelativePath: "src/a.go", StartLine: 5, EndLine: 6, Language: "go", RepoID: "repo-1"},
		},
	}

	stmts := writer.buildEntityStatements(mat)
	if got, want := len(stmts), 1; got != want {
		t.Fatalf("buildEntityStatements() count = %d, want %d", got, want)
	}

	rows, _ := stmts[0].Parameters["rows"].([]map[string]any)
	if _, ok := stmts[0].Parameters["file_path"]; ok {
		t.Fatalf("entity batch unexpectedly has statement-level file_path: %#v", stmts[0].Parameters)
	}
	if got, want := len(rows), 3; got != want {
		t.Fatalf("entity batch rows = %d, want %d", got, want)
	}
	for _, row := range rows {
		if _, ok := row["file_path"]; ok {
			t.Fatalf("entity row unexpectedly contains file_path: %#v", row)
		}
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

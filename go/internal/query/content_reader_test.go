package query

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"fmt"
	"io"
	"sync/atomic"
	"testing"
)

func TestContentReaderGetEntityContentIncludesMetadata(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"entity-1", "repo-1", "src/app.ts", "Function", "renderApp",
					int64(10), int64(24), "typescript", "function renderApp() {}", []byte(`{"docstring":"Renders the app.","decorators":["component"],"async":true}`),
				},
			},
		},
	})

	reader := NewContentReader(db)
	entity, err := reader.GetEntityContent(context.Background(), "entity-1")
	if err != nil {
		t.Fatalf("GetEntityContent() error = %v, want nil", err)
	}
	if entity == nil {
		t.Fatal("GetEntityContent() = nil, want non-nil")
	}

	if got, want := entity.Metadata["docstring"], "Renders the app."; got != want {
		t.Fatalf("Metadata[docstring] = %#v, want %#v", got, want)
	}
	if got, want := entity.Metadata["async"], true; got != want {
		t.Fatalf("Metadata[async] = %#v, want %#v", got, want)
	}

	decorators, ok := entity.Metadata["decorators"].([]any)
	if !ok {
		t.Fatalf("Metadata[decorators] type = %T, want []any", entity.Metadata["decorators"])
	}
	if len(decorators) != 1 || decorators[0] != "component" {
		t.Fatalf("Metadata[decorators] = %#v, want [component]", decorators)
	}
}

func TestContentReaderSearchEntityContentIncludesMetadata(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"entity-1", "repo-1", "src/app.tsx", "Function", "renderApp",
					int64(10), int64(24), "tsx", "function renderApp() {}", []byte(`{"method_kind":"component","jsx_component_usage":["Button"]}`),
				},
			},
		},
	})

	reader := NewContentReader(db)
	results, err := reader.SearchEntityContent(context.Background(), "repo-1", "render", 10)
	if err != nil {
		t.Fatalf("SearchEntityContent() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}

	if got, want := results[0].Metadata["method_kind"], "component"; got != want {
		t.Fatalf("Metadata[method_kind] = %#v, want %#v", got, want)
	}
	usage, ok := results[0].Metadata["jsx_component_usage"].([]any)
	if !ok {
		t.Fatalf("Metadata[jsx_component_usage] type = %T, want []any", results[0].Metadata["jsx_component_usage"])
	}
	if len(usage) != 1 || usage[0] != "Button" {
		t.Fatalf("Metadata[jsx_component_usage] = %#v, want [Button]", usage)
	}
}

func TestContentReaderListRepoEntitiesIncludesMetadata(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"alias-1", "repo-1", "src/types.ts", "TypeAlias", "UserID",
					int64(3), int64(3), "typescript", "type UserID = string", []byte(`{"type":"string","type_parameters":["T"]}`),
				},
			},
		},
	})

	reader := NewContentReader(db)
	results, err := reader.ListRepoEntities(context.Background(), "repo-1", 10)
	if err != nil {
		t.Fatalf("ListRepoEntities() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}

	if got, want := results[0].Metadata["type"], "string"; got != want {
		t.Fatalf("Metadata[type] = %#v, want %#v", got, want)
	}
	params, ok := results[0].Metadata["type_parameters"].([]any)
	if !ok {
		t.Fatalf("Metadata[type_parameters] type = %T, want []any", results[0].Metadata["type_parameters"])
	}
	if len(params) != 1 || params[0] != "T" {
		t.Fatalf("Metadata[type_parameters] = %#v, want [T]", params)
	}
}

func TestContentReaderListRepoFilesIncludesArtifactType(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"repo_id", "relative_path", "commit_sha", "content",
				"content_hash", "line_count", "language", "artifact_type",
			},
			rows: [][]driver.Value{
				{
					"repo-1", ".github/workflows/deploy.yaml", "abc123", "",
					"hash-1", int64(20), "yaml", "github_actions_workflow",
				},
			},
		},
	})

	reader := NewContentReader(db)
	results, err := reader.ListRepoFiles(context.Background(), "repo-1", 10)
	if err != nil {
		t.Fatalf("ListRepoFiles() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}
	if got, want := results[0].ArtifactType, "github_actions_workflow"; got != want {
		t.Fatalf("ArtifactType = %q, want %q", got, want)
	}
}

func TestContentReaderGetEntityContentRejectsInvalidMetadata(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"entity-1", "repo-1", "src/app.py", "Function", "handler",
					int64(1), int64(5), "python", "def handler(): pass", []byte(`{bad json}`),
				},
			},
		},
	})

	reader := NewContentReader(db)
	_, err := reader.GetEntityContent(context.Background(), "entity-1")
	if err == nil {
		t.Fatal("GetEntityContent() error = nil, want non-nil")
	}
}

func TestCodeHandlerSearchEntityContentIncludesMetadata(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{},
		},
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"entity-1", "repo-1", "src/app.py", "Function", "handler",
					int64(1), int64(5), "python", "async def handler(): ...", []byte(`{"decorators":["route"],"async":true}`),
				},
			},
		},
	})

	handler := &CodeHandler{Content: NewContentReader(db)}
	results, err := handler.searchEntityContent(context.Background(), "repo-1", "handler", "", 10)
	if err != nil {
		t.Fatalf("searchEntityContent() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}

	metadata, ok := results[0]["metadata"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][metadata] type = %T, want map[string]any", results[0]["metadata"])
	}
	if got, want := metadata["async"], true; got != want {
		t.Fatalf("metadata[async] = %#v, want %#v", got, want)
	}
}

func TestCodeHandlerSearchEntityContentIncludesEntityNameMatches(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"component-1", "repo-1", "src/Button.tsx", "Component", "Button",
					int64(1), int64(10), "tsx", "export default memo(() => null)", []byte(`{"framework":"react"}`),
				},
			},
		},
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{},
		},
	})

	handler := &CodeHandler{Content: NewContentReader(db)}
	results, err := handler.searchEntityContent(context.Background(), "repo-1", "Button", "typescript", 10)
	if err != nil {
		t.Fatalf("searchEntityContent() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}
	if got, want := results[0]["entity_name"], "Button"; got != want {
		t.Fatalf("results[0][entity_name] = %#v, want %#v", got, want)
	}
	if got, want := results[0]["language"], "tsx"; got != want {
		t.Fatalf("results[0][language] = %#v, want %#v", got, want)
	}
	if got, want := results[0]["semantic_summary"], "Component Button is associated with the react framework."; got != want {
		t.Fatalf("results[0][semantic_summary] = %#v, want %#v", got, want)
	}
	semanticProfile, ok := results[0]["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][semantic_profile] type = %T, want map[string]any", results[0]["semantic_profile"])
	}
	if got, want := semanticProfile["surface_kind"], "framework_component"; got != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", got, want)
	}
	if got, want := semanticProfile["framework"], "react"; got != want {
		t.Fatalf("semantic_profile[framework] = %#v, want %#v", got, want)
	}
}

func TestContentReaderSearchEntitiesByLanguageAndTypeIncludesLanguageVariants(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"component-1", "repo-1", "src/Button.tsx", "Component", "Button",
					int64(1), int64(10), "tsx", "export function Button() {}", []byte(`{"framework":"react"}`),
				},
			},
		},
	})

	reader := NewContentReader(db)
	results, err := reader.SearchEntitiesByLanguageAndType(context.Background(), "repo-1", "typescript", "Component", "Button", 10)
	if err != nil {
		t.Fatalf("SearchEntitiesByLanguageAndType() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}
	if got, want := results[0].Language, "tsx"; got != want {
		t.Fatalf("results[0].Language = %#v, want %#v", got, want)
	}
	if got, want := results[0].Metadata["framework"], "react"; got != want {
		t.Fatalf("results[0].Metadata[framework] = %#v, want %#v", got, want)
	}
}

func TestContentReaderSearchEntitiesReferencingComponent(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"function-1", "repo-1", "src/App.tsx", "Function", "renderApp",
					int64(5), int64(20), "tsx", "return <Button />", []byte(`{"jsx_component_usage":["Button","Panel"]}`),
				},
			},
		},
	})

	reader := NewContentReader(db)
	results, err := reader.SearchEntitiesReferencingComponent(context.Background(), "repo-1", "Button", 10)
	if err != nil {
		t.Fatalf("SearchEntitiesReferencingComponent() error = %v, want nil", err)
	}
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}
	if got, want := results[0].EntityName, "renderApp"; got != want {
		t.Fatalf("results[0].EntityName = %#v, want %#v", got, want)
	}
	usage, ok := results[0].Metadata["jsx_component_usage"].([]any)
	if !ok {
		t.Fatalf("Metadata[jsx_component_usage] type = %T, want []any", results[0].Metadata["jsx_component_usage"])
	}
	if len(usage) != 2 || usage[0] != "Button" || usage[1] != "Panel" {
		t.Fatalf("Metadata[jsx_component_usage] = %#v, want [Button Panel]", usage)
	}
}

type contentReaderQueryResult struct {
	columns []string
	rows    [][]driver.Value
	err     error
}

func openContentReaderTestDB(t *testing.T, results []contentReaderQueryResult) *sql.DB {
	t.Helper()

	name := fmt.Sprintf("content-reader-test-%d", atomic.AddUint64(&contentReaderDriverSeq, 1))
	sql.Register(name, &contentReaderDriver{results: results})

	db, err := sql.Open(name, "")
	if err != nil {
		t.Fatalf("sql.Open() error = %v, want nil", err)
	}
	t.Cleanup(func() {
		_ = db.Close()
	})
	return db
}

var contentReaderDriverSeq uint64

type contentReaderDriver struct {
	results []contentReaderQueryResult
}

func (d *contentReaderDriver) Open(string) (driver.Conn, error) {
	return &contentReaderConn{results: append([]contentReaderQueryResult(nil), d.results...)}, nil
}

type contentReaderConn struct {
	results []contentReaderQueryResult
}

func (c *contentReaderConn) Prepare(string) (driver.Stmt, error) {
	return nil, fmt.Errorf("Prepare not implemented")
}

func (c *contentReaderConn) Close() error {
	return nil
}

func (c *contentReaderConn) Begin() (driver.Tx, error) {
	return nil, fmt.Errorf("Begin not implemented")
}

func (c *contentReaderConn) QueryContext(context.Context, string, []driver.NamedValue) (driver.Rows, error) {
	if len(c.results) == 0 {
		return nil, fmt.Errorf("unexpected query")
	}
	result := c.results[0]
	c.results = c.results[1:]
	if result.err != nil {
		return nil, result.err
	}
	return &contentReaderRows{columns: result.columns, rows: result.rows}, nil
}

type contentReaderRows struct {
	columns []string
	rows    [][]driver.Value
	index   int
}

func (r *contentReaderRows) Columns() []string {
	return r.columns
}

func (r *contentReaderRows) Close() error {
	return nil
}

func (r *contentReaderRows) Next(dest []driver.Value) error {
	if r.index >= len(r.rows) {
		return io.EOF
	}
	copy(dest, r.rows[r.index])
	r.index++
	return nil
}

func TestContentReaderMetadataFixtureIsValidJSON(t *testing.T) {
	t.Parallel()

	payload := []byte(`{"docstring":"ok","decorators":["component"],"async":true}`)
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}
}

func TestParseFrameworkSemanticsExtractsHapiAndExpressRoutes(t *testing.T) {
	t.Parallel()

	raw := []byte(`{
		"frameworks": ["hapi", "express"],
		"hapi": {
			"route_methods": ["GET", "POST"],
			"route_paths": ["/elastic", "/alias/{index}/create"],
			"server_symbols": ["server"]
		},
		"express": {
			"route_methods": ["GET"],
			"route_paths": ["/health"],
			"server_symbols": ["app"]
		}
	}`)

	results := parseFrameworkSemantics("src/routes.js", raw)
	if len(results) != 2 {
		t.Fatalf("len(results) = %d, want 2", len(results))
	}

	// Results are in framework order from JSON array
	hapi := results[0]
	if hapi.Framework != "hapi" {
		t.Fatalf("results[0].Framework = %q, want \"hapi\"", hapi.Framework)
	}
	if len(hapi.RoutePaths) != 2 {
		t.Fatalf("hapi.RoutePaths = %v, want 2 paths", hapi.RoutePaths)
	}
	if hapi.RelativePath != "src/routes.js" {
		t.Fatalf("hapi.RelativePath = %q, want \"src/routes.js\"", hapi.RelativePath)
	}

	express := results[1]
	if express.Framework != "express" {
		t.Fatalf("results[1].Framework = %q, want \"express\"", express.Framework)
	}
	if len(express.RoutePaths) != 1 || express.RoutePaths[0] != "/health" {
		t.Fatalf("express.RoutePaths = %v, want [\"/health\"]", express.RoutePaths)
	}
}

func TestParseFrameworkSemanticsSkipsEmptyFrameworks(t *testing.T) {
	t.Parallel()

	raw := []byte(`{"frameworks": []}`)
	results := parseFrameworkSemantics("file.py", raw)
	if len(results) != 0 {
		t.Fatalf("len(results) = %d, want 0 for empty frameworks", len(results))
	}
}

func TestParseFrameworkSemanticsSkipsFrameworkWithNoRoutes(t *testing.T) {
	t.Parallel()

	raw := []byte(`{
		"frameworks": ["fastapi"],
		"fastapi": {
			"route_methods": ["GET"],
			"route_paths": [],
			"server_symbols": ["app"]
		}
	}`)

	results := parseFrameworkSemantics("api/main.py", raw)
	if len(results) != 0 {
		t.Fatalf("len(results) = %d, want 0 for framework with empty route_paths", len(results))
	}
}

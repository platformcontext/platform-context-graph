package main

import (
	"context"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
)

func TestNornicDBSyntaxVerification(t *testing.T) {
	withNornicDBSyntaxDriver(t, func(ctx context.Context, driver neo4jdriver.DriverWithContext) {
		tests := []struct {
			name   string
			cypher string
		}{
			{
				name:   "fulltext index",
				cypher: "CREATE FULLTEXT INDEX pcg_syntax_fulltext IF NOT EXISTS FOR (n:PCGSyntaxFunction|PCGSyntaxClass|PCGSyntaxVariable) ON EACH [n.name, n.source, n.docstring]",
			},
			{
				name:   "fulltext procedure fallback",
				cypher: "CALL db.index.fulltext.createNodeIndex('pcg_syntax_fulltext_proc', ['PCGSyntaxFunction', 'PCGSyntaxClass', 'PCGSyntaxVariable'], ['name', 'source', 'docstring'])",
			},
			{
				name:   "collect distinct map literal",
				cypher: "WITH 1 AS ignored RETURN COLLECT(DISTINCT {id: 'f1', name: 'parse_config', path: 'src/config.go'}) AS items",
			},
		}
		runNornicDBSyntaxCases(t, ctx, driver, tests)
	})
}

func TestNornicDBCompatibilityWorkarounds(t *testing.T) {
	withNornicDBSyntaxDriver(t, func(ctx context.Context, driver neo4jdriver.DriverWithContext) {
		tests := []struct {
			name   string
			cypher string
		}{
			{
				name:   "composite node key alternative",
				cypher: "CREATE CONSTRAINT pcg_syntax_function_node_key IF NOT EXISTS FOR (f:PCGSyntaxFunction) REQUIRE (f.name, f.path, f.line_number) IS NODE KEY",
			},
			{
				name:   "multi label fulltext procedure",
				cypher: "CALL db.index.fulltext.createNodeIndex('pcg_syntax_workaround_fulltext', ['PCGSyntaxFunction', 'PCGSyntaxClass', 'PCGSyntaxVariable'], ['name', 'source', 'docstring'])",
			},
			{
				name:   "file path merge lookup index",
				cypher: "CREATE INDEX pcg_syntax_file_path_lookup IF NOT EXISTS FOR (f:File) ON (f.path)",
			},
			{
				name:   "directory path merge lookup index",
				cypher: "CREATE INDEX pcg_syntax_directory_path_lookup IF NOT EXISTS FOR (d:Directory) ON (d.path)",
			},
			{
				name:   "repository id merge lookup index",
				cypher: "CREATE INDEX pcg_syntax_repository_id_lookup IF NOT EXISTS FOR (r:Repository) ON (r.id)",
			},
			{
				name:   "workload id merge lookup index",
				cypher: "CREATE INDEX pcg_syntax_workload_id_lookup IF NOT EXISTS FOR (w:Workload) ON (w.id)",
			},
			{
				name:   "uid merge lookup index",
				cypher: "CREATE INDEX pcg_syntax_function_uid_lookup IF NOT EXISTS FOR (f:PCGSyntaxFunction) ON (f.uid)",
			},
		}
		runNornicDBSyntaxCases(t, ctx, driver, tests)
	})
}

func TestNornicDBBatchedEntityContainmentHotPathCompatibility(t *testing.T) {
	withNornicDBSyntaxDriver(t, func(ctx context.Context, driver neo4jdriver.DriverWithContext) {
		setup := []string{
			"CREATE CONSTRAINT pcg_syntax_function_uid IF NOT EXISTS FOR (n:Function) REQUIRE n.uid IS UNIQUE",
			"CREATE CONSTRAINT pcg_syntax_file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
			"MERGE (:File {path: '/tmp/pcg-nornicdb-batch/main.go'})",
		}
		runNornicDBSyntaxSequence(t, ctx, driver, setup)

		nodeQuery := `UNWIND $rows AS row
MERGE (n:Function {uid: row.entity_id})
SET n += row.props
MATCH (f:File {path: row.file_path})
MERGE (f)-[:CONTAINS]->(n)
RETURN count(*) AS processed_rows`

		rows := []map[string]any{
			{
				"file_path":  "/tmp/pcg-nornicdb-batch/main.go",
				"entity_id":  "fn:one",
				"entityID":   "fn:one",
				"primaryKey": "fn:one",
				"props": map[string]any{
					"id":            "fn:one",
					"name":          "handleRelationships",
					"path":          "/tmp/pcg-nornicdb-batch/main.go",
					"relative_path": "main.go",
					"line_number":   10,
					"start_line":    10,
					"end_line":      20,
					"repo_id":       "repo-batch",
					"language":      "go",
					"lang":          "go",
					"scope_id":      "scope-batch",
					"generation_id": "gen-batch",
				},
			},
			{
				"file_path":  "/tmp/pcg-nornicdb-batch/main.go",
				"entity_id":  "fn:two",
				"entityID":   "fn:two",
				"primaryKey": "fn:two",
				"props": map[string]any{
					"id":            "fn:two",
					"name":          "transitiveRelationshipsGraphResponse",
					"path":          "/tmp/pcg-nornicdb-batch/main.go",
					"relative_path": "main.go",
					"line_number":   30,
					"start_line":    30,
					"end_line":      40,
					"repo_id":       "repo-batch",
					"language":      "go",
					"lang":          "go",
					"scope_id":      "scope-batch",
					"generation_id": "gen-batch",
				},
			},
		}

		session := driver.NewSession(ctx, neo4jdriver.SessionConfig{
			AccessMode:   neo4jdriver.AccessModeWrite,
			DatabaseName: localNornicDBDefaultDatabase,
		})
		defer func() {
			_ = session.Close(ctx)
		}()

		result, err := session.Run(ctx, nodeQuery, map[string]any{
			"rows": rows,
		})
		if err != nil {
			t.Fatalf("batched canonical entity query error = %v, want nil", err)
		}
		if _, err := result.Consume(ctx); err != nil {
			t.Fatalf("batched canonical entity consume error = %v, want nil", err)
		}
		nodeCount, err := nornicDBReadCount(ctx, driver, `
MATCH (f:Function)
RETURN count(f) AS count`, nil)
		if err != nil {
			t.Fatalf("count batched canonical functions before containment error = %v, want nil", err)
		}
		if nodeCount != 2 {
			t.Fatalf("batched canonical function node count = %d, want 2", nodeCount)
		}
		nodeCountWithRepo, err := nornicDBReadCount(ctx, driver, `
MATCH (f:Function)
WHERE f.repo_id = $repo_id
RETURN count(f) AS count`, map[string]any{
			"repo_id": "repo-batch",
		})
		if err != nil {
			t.Fatalf("count batched canonical functions with repo before containment error = %v, want nil", err)
		}
		if nodeCountWithRepo != 2 {
			t.Fatalf("batched canonical function node count with repo = %d, want 2", nodeCountWithRepo)
		}
		count, err := nornicDBReadCount(ctx, driver, `
MATCH (:File {path: $file_path})-[:CONTAINS]->(f:Function)
WHERE f.repo_id = $repo_id
RETURN count(f) AS count`, map[string]any{
			"file_path": "/tmp/pcg-nornicdb-batch/main.go",
			"repo_id":   "repo-batch",
		})
		if err != nil {
			t.Fatalf("count batched canonical functions error = %v, want nil", err)
		}
		if count != 2 {
			t.Fatalf("batched canonical function count = %d, want 2", count)
		}
	})
}

func TestNornicDBCanonicalEntitySingletonFallbackForShortestPathValues(t *testing.T) {
	withNornicDBSyntaxDriver(t, func(ctx context.Context, driver neo4jdriver.DriverWithContext) {
		setup := []string{
			"MERGE (:File {path: '/tmp/pcg-nornicdb-batch/main.go'})",
		}
		runNornicDBSyntaxSequence(t, ctx, driver, setup)

		batchedQuery := `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Function {uid: row.entity_id})
SET n += row.props
MERGE (f)-[:CONTAINS]->(n)
RETURN count(*) AS processed_rows`

		normalRows := []map[string]any{
			{
				"file_path": "/tmp/pcg-nornicdb-batch/main.go",
				"entity_id": "fn:one",
				"props": map[string]any{
					"id":            "fn:one",
					"name":          "handleRelationships",
					"path":          "/tmp/pcg-nornicdb-batch/main.go",
					"relative_path": "main.go",
					"line_number":   10,
					"start_line":    10,
					"end_line":      20,
					"repo_id":       "repo-batch",
					"language":      "go",
					"lang":          "go",
					"scope_id":      "scope-batch",
					"generation_id": "gen-batch",
				},
			},
		}
		singletonQuery := `MATCH (f:File {path: $file_path})
MERGE (n:Function {uid: $entity_id})
SET n += $props
MERGE (f)-[:CONTAINS]->(n)
RETURN count(*) AS processed_rows`
		shortestPathRow := map[string]any{
			"file_path": "/tmp/pcg-nornicdb-batch/main.go",
			"entity_id": "fn:two",
			"props": map[string]any{
				"id":            "fn:two",
				"name":          "TestHandleCallChainReturnsShortestPath",
				"path":          "/tmp/pcg-nornicdb-batch/main.go",
				"relative_path": "main.go",
				"line_number":   30,
				"start_line":    30,
				"end_line":      40,
				"repo_id":       "repo-batch",
				"language":      "go",
				"lang":          "go",
				"scope_id":      "scope-batch",
				"generation_id": "gen-batch",
			},
		}

		session := driver.NewSession(ctx, neo4jdriver.SessionConfig{
			AccessMode:   neo4jdriver.AccessModeWrite,
			DatabaseName: localNornicDBDefaultDatabase,
		})
		defer func() {
			_ = session.Close(ctx)
		}()

		result, err := session.Run(ctx, batchedQuery, map[string]any{"rows": normalRows})
		if err != nil {
			t.Fatalf("batched canonical entity query error = %v, want nil", err)
		}
		if _, err := result.Consume(ctx); err != nil {
			t.Fatalf("batched canonical entity consume error = %v, want nil", err)
		}

		result, err = session.Run(ctx, singletonQuery, shortestPathRow)
		if err != nil {
			t.Fatalf("singleton canonical entity query error = %v, want nil", err)
		}
		if _, err := result.Consume(ctx); err != nil {
			t.Fatalf("singleton canonical entity consume error = %v, want nil", err)
		}

		count, err := nornicDBReadCount(ctx, driver, `
MATCH (:File {path: $file_path})-[:CONTAINS]->(f:Function)
WHERE f.repo_id = $repo_id
RETURN count(f) AS count`, map[string]any{
			"file_path": "/tmp/pcg-nornicdb-batch/main.go",
			"repo_id":   "repo-batch",
		})
		if err != nil {
			t.Fatalf("count fallback canonical functions error = %v, want nil", err)
		}
		if count != 2 {
			t.Fatalf("fallback canonical function count = %d, want 2", count)
		}
	})
}

func TestNornicDBSharedEdgeWriteCompatibilityWorkarounds(t *testing.T) {
	withNornicDBSyntaxDriver(t, func(ctx context.Context, driver neo4jdriver.DriverWithContext) {
		setup := []string{
			"MERGE (:PCGSyntaxFunction {uid: 'caller'})",
			"MERGE (:PCGSyntaxFunction {uid: 'callee'})",
			"MERGE (:PCGSyntaxClass {uid: 'child'})",
			"MERGE (:PCGSyntaxClass {uid: 'parent'})",
			"MERGE (:PCGSyntaxSqlTable {uid: 'table'})",
			"MERGE (:PCGSyntaxSqlColumn {uid: 'column'})",
		}
		runNornicDBSyntaxSequence(t, ctx, driver, setup)

		tests := []struct {
			name   string
			cypher string
		}{
			{
				name: `shared code-call write`,
				cypher: `MATCH (source:PCGSyntaxFunction {uid: 'caller'})
MATCH (target:PCGSyntaxFunction {uid: 'callee'})
MERGE (source)-[rel:CALLS]->(target)
SET rel.confidence = 0.95,
    rel.reason = 'Parser and symbol analysis resolved a code call edge',
    rel.evidence_source = 'parser/code-calls'`,
			},
			{
				name: `shared inheritance write`,
				cypher: `MATCH (child:PCGSyntaxClass {uid: 'child'})
MATCH (parent:PCGSyntaxClass {uid: 'parent'})
MERGE (child)-[rel:INHERITS]->(parent)
SET rel.confidence = 0.95,
    rel.reason = 'Parser entity bases metadata resolved an inheritance edge',
    rel.evidence_source = 'reducer/inheritance',
    rel.relationship_type = 'INHERITS'`,
			},
			{
				name: `shared sql write`,
				cypher: `MATCH (source:PCGSyntaxSqlTable {uid: 'table'})
MATCH (target:PCGSyntaxSqlColumn {uid: 'column'})
MERGE (source)-[rel:HAS_COLUMN]->(target)
SET rel.confidence = 0.95,
    rel.reason = 'SQL entity metadata resolved a table-column containment edge',
    rel.evidence_source = 'reducer/sql-relationships'`,
			},
		}
		runNornicDBSyntaxCases(t, ctx, driver, tests)
	})
}

func TestNornicDBSchemaAdapterVerification(t *testing.T) {
	withNornicDBSyntaxDriver(t, func(ctx context.Context, driver neo4jdriver.DriverWithContext) {
		stmts, err := graph.SchemaStatementsForBackend(graph.SchemaBackendNornicDB)
		if err != nil {
			t.Fatalf("SchemaStatementsForBackend(%q) error = %v, want nil", graph.SchemaBackendNornicDB, err)
		}
		for _, stmt := range stmts {
			if err := runNornicDBSyntaxCypher(ctx, driver, stmt); err != nil {
				t.Fatalf("run adapted schema statement %q error = %v", stmt, err)
			}
		}
	})
}

func withNornicDBSyntaxDriver(t *testing.T, fn func(context.Context, neo4jdriver.DriverWithContext)) {
	t.Helper()

	if strings.TrimSpace(os.Getenv("PCG_NORNICDB_BINARY")) == "" {
		t.Skip("set PCG_NORNICDB_BINARY to run the NornicDB syntax compatibility gate")
	}

	binaryPath, err := resolveNornicDBBinary()
	if err != nil {
		t.Fatalf("resolveNornicDBBinary() error = %v", err)
	}
	t.Logf("using NornicDB binary %s", binaryPath)

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	root := t.TempDir()
	graph, err := startManagedLocalNornicDB(ctx, pcglocal.Layout{
		GraphDir: filepath.Join(root, "graph"),
		LogsDir:  filepath.Join(root, "logs"),
	})
	if err != nil {
		t.Fatalf("startManagedLocalNornicDB() error = %v", err)
	}
	t.Cleanup(func() {
		if err := stopManagedLocalGraph(graph, localGraphShutdownTimeout); err != nil {
			t.Errorf("stopManagedLocalGraph() error = %v, want nil", err)
		}
	})

	driver, err := neo4jdriver.NewDriverWithContext(
		"bolt://"+graph.Address+":"+strconv.Itoa(graph.BoltPort),
		neo4jdriver.BasicAuth(graph.Username, graph.Password, ""),
	)
	if err != nil {
		t.Fatalf("NewDriverWithContext() error = %v, want nil", err)
	}
	t.Cleanup(func() {
		_ = driver.Close(context.Background())
	})
	if err := driver.VerifyConnectivity(ctx); err != nil {
		t.Fatalf("VerifyConnectivity() error = %v, want nil", err)
	}

	fn(ctx, driver)
}

func runNornicDBSyntaxCases(t *testing.T, ctx context.Context, driver neo4jdriver.DriverWithContext, tests []struct {
	name   string
	cypher string
}) {
	t.Helper()

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			if err := runNornicDBSyntaxCypher(ctx, driver, tt.cypher); err != nil {
				t.Fatalf("run syntax probe %q error = %v", tt.name, err)
			}
		})
	}
}

func runNornicDBSyntaxSequence(t *testing.T, ctx context.Context, driver neo4jdriver.DriverWithContext, statements []string) {
	t.Helper()

	for _, stmt := range statements {
		if err := runNornicDBSyntaxCypher(ctx, driver, stmt); err != nil {
			t.Fatalf("run setup statement %q error = %v", stmt, err)
		}
	}
}

func runNornicDBSyntaxCypher(ctx context.Context, driver neo4jdriver.DriverWithContext, cypher string) error {
	session := driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeWrite,
		DatabaseName: localNornicDBDefaultDatabase,
	})
	defer func() {
		_ = session.Close(ctx)
	}()

	result, err := session.Run(ctx, cypher, map[string]any{})
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
}

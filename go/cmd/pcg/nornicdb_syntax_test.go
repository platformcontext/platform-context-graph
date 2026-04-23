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

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
)

func TestNornicDBSyntaxVerification(t *testing.T) {
	withNornicDBSyntaxDriver(t, func(ctx context.Context, driver neo4jdriver.DriverWithContext) {
		tests := []struct {
			name   string
			cypher string
		}{
			{
				name:   "composite unique constraint",
				cypher: "CREATE CONSTRAINT pcg_syntax_function_unique IF NOT EXISTS FOR (f:PCGSyntaxFunction) REQUIRE (f.name, f.path, f.line_number) IS UNIQUE",
			},
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
		}
		runNornicDBSyntaxCases(t, ctx, driver, tests)
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

package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	pythonbridge "github.com/platformcontext/platform-context-graph/go/internal/compatibility/pythonbridge"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const bootstrapIndexConnectionTimeout = 10 * time.Second

func buildBootstrapCollector(
	ctx context.Context,
	database bootstrapDB,
	getenv func(string) string,
) (collectorDeps, error) {
	sqlDB, ok := database.(postgres.ExecQueryer)
	if !ok {
		return collectorDeps{}, fmt.Errorf("bootstrap collector requires a SQL database")
	}

	repoRoot, err := resolveBootstrapRepoRoot(getenv, os.Getwd)
	if err != nil {
		return collectorDeps{}, err
	}

	environ := os.Environ()
	source := &collector.GitSource{
		Component: "bootstrap-index",
		Selector: pythonbridge.GitSelectionRunner{
			PythonExecutable: getenv("PCG_PYTHON_EXECUTABLE"),
			RepoRoot:         repoRoot,
			Env:              environ,
		},
		Snapshotter: pythonbridge.GitRepositorySnapshotRunner{
			PythonExecutable: getenv("PCG_PYTHON_EXECUTABLE"),
			RepoRoot:         repoRoot,
			Env:              environ,
		},
	}

	return collectorDeps{
		source:    source,
		committer: postgres.NewIngestionStore(sqlDB),
	}, nil
}

func buildBootstrapProjector(
	ctx context.Context,
	database bootstrapDB,
	graphWriter graph.Writer,
	getenv func(string) string,
) (projectorDeps, error) {
	sqlDB, ok := database.(postgres.ExecQueryer)
	if !ok {
		return projectorDeps{}, fmt.Errorf("bootstrap projector requires a SQL database")
	}

	projectorQueue := postgres.NewProjectorQueue(sqlDB, "bootstrap-index", time.Minute)
	reducerQueue := postgres.NewReducerQueue(sqlDB, "bootstrap-index", time.Minute)
	runtime := projector.Runtime{
		GraphWriter:   graphWriter,
		ContentWriter: postgres.NewContentWriter(sqlDB),
		IntentWriter:  reducerQueue,
	}

	return projectorDeps{
		workSource: projectorQueue,
		factStore:  postgres.NewFactStore(sqlDB),
		runner:     runtime,
		workSink:   projectorQueue,
	}, nil
}

func openBootstrapGraphWriter(
	parent context.Context,
	getenv func(string) string,
) (graph.Writer, io.Closer, error) {
	driver, cfg, err := runtimecfg.OpenNeo4jDriver(parent, getenv)
	if err != nil {
		return nil, nil, err
	}

	return sourceneo4j.Adapter{
			Executor: bootstrapNeo4jExecutor{
				Driver:       driver,
				DatabaseName: cfg.DatabaseName,
			},
		},
		bootstrapNeo4jDriverCloser{Driver: driver},
		nil
}

type bootstrapNeo4jExecutor struct {
	Driver       neo4jdriver.DriverWithContext
	DatabaseName string
}

func (e bootstrapNeo4jExecutor) Execute(ctx context.Context, statement sourceneo4j.Statement) error {
	if e.Driver == nil {
		return fmt.Errorf("neo4j driver is required")
	}

	session := e.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
		AccessMode:   neo4jdriver.AccessModeWrite,
		DatabaseName: e.DatabaseName,
	})
	defer session.Close(ctx)

	result, err := session.Run(ctx, statement.Cypher, statement.Parameters)
	if err != nil {
		return err
	}
	_, err = result.Consume(ctx)
	return err
}

type bootstrapNeo4jDriverCloser struct {
	Driver neo4jdriver.DriverWithContext
}

func (c bootstrapNeo4jDriverCloser) Close() error {
	return closeBootstrapNeo4jDriver(c.Driver)
}

func closeBootstrapNeo4jDriver(driver neo4jdriver.DriverWithContext) error {
	if driver == nil {
		return nil
	}

	closeCtx, cancel := context.WithTimeout(context.Background(), bootstrapIndexConnectionTimeout)
	defer cancel()
	return driver.Close(closeCtx)
}

// resolveBootstrapRepoRoot locates the Python bridge repo root for the
// bootstrap-index collector. This duplicates the collector-git helper because
// both live in package main and cannot be shared.
func resolveBootstrapRepoRoot(
	getenv func(string) string,
	getwd func() (string, error),
) (string, error) {
	candidates := make([]string, 0, 3)

	if configured := strings.TrimSpace(getenv("PCG_REPO_ROOT")); configured != "" {
		candidates = append(candidates, configured)
	}

	workingDirectory, err := getwd()
	if err != nil {
		return "", fmt.Errorf("determine working directory for bootstrap-index bridge: %w", err)
	}
	candidates = append(candidates, workingDirectory)
	candidates = append(candidates, filepath.Dir(workingDirectory))

	for _, candidate := range candidates {
		resolved, err := filepath.Abs(candidate)
		if err != nil {
			continue
		}
		if bootstrapBridgeRepoRootExists(resolved) {
			return resolved, nil
		}
	}

	return "", fmt.Errorf(
		"bootstrap-index bridge repo root must contain src/platform_context_graph; set PCG_REPO_ROOT explicitly if needed",
	)
}

func bootstrapBridgeRepoRootExists(root string) bool {
	info, err := os.Stat(filepath.Join(root, "src", "platform_context_graph"))
	if err != nil {
		return false
	}
	return info.IsDir()
}

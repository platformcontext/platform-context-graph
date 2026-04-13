package main

import (
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	pythonbridge "github.com/platformcontext/platform-context-graph/go/internal/compatibility/pythonbridge"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const defaultCollectorPollInterval = time.Second

func buildCollectorService(
	database postgres.SQLDB,
	getenv func(string) string,
	getwd func() (string, error),
	environ func() []string,
) (collector.Service, error) {
	repoRoot, err := resolveCollectorRepoRoot(getenv, getwd)
	if err != nil {
		return collector.Service{}, err
	}

	return collector.Service{
		Source: &collector.GitSource{
			Component: "collector-git",
			Selector: pythonbridge.GitSelectionRunner{
				PythonExecutable: getenv("PCG_PYTHON_EXECUTABLE"),
				RepoRoot:         repoRoot,
				Env:              environ(),
			},
			Snapshotter: pythonbridge.GitRepositorySnapshotRunner{
				PythonExecutable: getenv("PCG_PYTHON_EXECUTABLE"),
				RepoRoot:         repoRoot,
				Env:              environ(),
			},
		},
		Committer:    postgres.NewIngestionStore(database),
		PollInterval: defaultCollectorPollInterval,
	}, nil
}

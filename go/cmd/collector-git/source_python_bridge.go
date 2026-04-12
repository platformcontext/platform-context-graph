package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	pythonbridge "github.com/platformcontext/platform-context-graph/go/internal/compatibility/pythonbridge"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func buildCollectorService(
	database postgres.SQLDB,
	getenv func(string) string,
	getwd func() (string, error),
	environ func() []string,
) (Service, error) {
	repoRoot, err := resolveCollectorRepoRoot(getenv, getwd)
	if err != nil {
		return Service{}, err
	}

	return Service{
		Source: &pythonbridge.BufferedSource{
			Runner: pythonbridge.GitCollectorRunner{
				PythonExecutable: getenv("PCG_PYTHON_EXECUTABLE"),
				RepoRoot:         repoRoot,
				Env:              environ(),
			},
		},
		Committer:    postgres.NewIngestionStore(database),
		PollInterval: defaultCollectorPollInterval,
	}, nil
}

func resolveCollectorRepoRoot(
	getenv func(string) string,
	getwd func() (string, error),
) (string, error) {
	candidates := make([]string, 0, 3)

	if configured := strings.TrimSpace(getenv("PCG_REPO_ROOT")); configured != "" {
		candidates = append(candidates, configured)
	}

	workingDirectory, err := getwd()
	if err != nil {
		return "", fmt.Errorf("determine working directory for collector bridge: %w", err)
	}
	candidates = append(candidates, workingDirectory)
	candidates = append(candidates, filepath.Dir(workingDirectory))

	for _, candidate := range candidates {
		resolved, err := filepath.Abs(candidate)
		if err != nil {
			continue
		}
		if bridgeRepoRootExists(resolved) {
			return resolved, nil
		}
	}

	return "", fmt.Errorf(
		"collector bridge repo root must contain src/platform_context_graph; set PCG_REPO_ROOT explicitly if needed",
	)
}

func bridgeRepoRootExists(root string) bool {
	info, err := os.Stat(filepath.Join(root, "src", "platform_context_graph"))
	if err != nil {
		return false
	}
	return info.IsDir()
}

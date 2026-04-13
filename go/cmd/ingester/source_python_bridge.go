package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// resolveIngesterRepoRoot locates the Python bridge repo root for the ingester
// collector. This duplicates the collector-git helper because both live in
// package main and cannot be shared. It will be removed when Codex replaces
// the Python bridge with native Go implementations.
func resolveIngesterRepoRoot(
	getenv func(string) string,
	getwd func() (string, error),
) (string, error) {
	candidates := make([]string, 0, 3)

	if configured := strings.TrimSpace(getenv("PCG_REPO_ROOT")); configured != "" {
		candidates = append(candidates, configured)
	}

	workingDirectory, err := getwd()
	if err != nil {
		return "", fmt.Errorf("determine working directory for ingester bridge: %w", err)
	}
	candidates = append(candidates, workingDirectory)
	candidates = append(candidates, filepath.Dir(workingDirectory))

	for _, candidate := range candidates {
		resolved, err := filepath.Abs(candidate)
		if err != nil {
			continue
		}
		if ingesterBridgeRepoRootExists(resolved) {
			return resolved, nil
		}
	}

	return "", fmt.Errorf(
		"ingester bridge repo root must contain src/platform_context_graph; set PCG_REPO_ROOT explicitly if needed",
	)
}

func ingesterBridgeRepoRootExists(root string) bool {
	info, err := os.Stat(filepath.Join(root, "src", "platform_context_graph"))
	if err != nil {
		return false
	}
	return info.IsDir()
}

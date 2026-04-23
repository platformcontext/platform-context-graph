package query

import (
	"context"
	"fmt"
	"slices"
	"strings"
)

func (h *CodeHandler) resolveRepositorySelector(ctx context.Context, selector string) (string, error) {
	selector = strings.TrimSpace(selector)
	if selector == "" {
		return "", nil
	}
	if looksCanonicalRepositoryID(selector) {
		return selector, nil
	}

	if h != nil && h.Content != nil {
		entries, err := h.Content.ListRepositories(ctx)
		if err != nil {
			return "", fmt.Errorf("list repositories: %w", err)
		}
		matches := resolveRepositoryCatalogMatches(entries, selector)
		switch len(matches) {
		case 0:
		case 1:
			return matches[0], nil
		default:
			return "", fmt.Errorf("repository selector %q matched multiple repositories: %s", selector, strings.Join(matches, ", "))
		}
	}

	if h != nil && h.Neo4j != nil {
		rows, err := h.Neo4j.Run(ctx, `
			MATCH (r:Repository)
			WHERE r.id = $repo_selector OR r.name = $repo_selector
			RETURN r.id as id
			ORDER BY r.id
		`, map[string]any{"repo_selector": selector})
		if err != nil {
			return "", fmt.Errorf("query graph repository selector: %w", err)
		}
		switch len(rows) {
		case 0:
		case 1:
			return StringVal(rows[0], "id"), nil
		default:
			ids := make([]string, 0, len(rows))
			for _, row := range rows {
				id := StringVal(row, "id")
				if id != "" {
					ids = append(ids, id)
				}
			}
			slices.Sort(ids)
			return "", fmt.Errorf("repository selector %q matched multiple repositories: %s", selector, strings.Join(ids, ", "))
		}
	}

	return "", fmt.Errorf("repository selector %q did not match any indexed repository", selector)
}

func looksCanonicalRepositoryID(selector string) bool {
	return strings.HasPrefix(selector, "repo-") || strings.HasPrefix(selector, "repository:")
}

func resolveRepositoryCatalogMatches(entries []RepositoryCatalogEntry, selector string) []string {
	if strings.TrimSpace(selector) == "" {
		return nil
	}
	matches := make([]string, 0, 1)
	seen := make(map[string]struct{})
	for _, entry := range entries {
		switch selector {
		case entry.ID, entry.Name, entry.Path, entry.LocalPath, entry.RemoteURL, entry.RepoSlug:
			if _, ok := seen[entry.ID]; ok || entry.ID == "" {
				continue
			}
			seen[entry.ID] = struct{}{}
			matches = append(matches, entry.ID)
		}
	}
	slices.Sort(matches)
	return matches
}

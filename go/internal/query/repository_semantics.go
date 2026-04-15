package query

import (
	"cmp"
	"context"
	"fmt"
	"slices"
)

const repositorySemanticEntityLimit = 5000

func buildRepositorySemanticOverview(entities []EntityContent) map[string]any {
	if len(entities) == 0 {
		return nil
	}

	languageCounts := map[string]int{}
	signalCounts := map[string]int{}
	surfaceKindCounts := map[string]int{}
	entityCount := 0

	for _, entity := range entities {
		result := map[string]any{
			"labels":   []string{entity.EntityType},
			"language": entity.Language,
			"metadata": entity.Metadata,
			"name":     entity.EntityName,
		}
		profile := buildEntitySemanticProfile(result)
		if len(profile) == 0 {
			continue
		}

		entityCount++
		if entity.Language != "" {
			languageCounts[entity.Language]++
		}
		if surfaceKind, ok := profile["surface_kind"].(string); ok && surfaceKind != "" {
			surfaceKindCounts[surfaceKind]++
		}
		if signals, ok := profile["signals"].([]string); ok {
			for _, signal := range signals {
				if signal != "" {
					signalCounts[signal]++
				}
			}
		}
	}

	if entityCount == 0 {
		return nil
	}

	return map[string]any{
		"entity_count":        entityCount,
		"language_counts":     languageCounts,
		"signal_counts":       signalCounts,
		"surface_kind_counts": surfaceKindCounts,
	}
}

func loadRepositorySemanticOverview(
	ctx context.Context,
	reader *ContentReader,
	repoID string,
) (map[string]any, error) {
	if reader == nil || repoID == "" {
		return nil, nil
	}

	entities, err := reader.ListRepoEntities(ctx, repoID, repositorySemanticEntityLimit)
	if err != nil {
		return nil, fmt.Errorf("list repository semantic entities: %w", err)
	}
	return buildRepositorySemanticOverview(entities), nil
}

func buildRepositorySemanticStory(overview map[string]any) string {
	if len(overview) == 0 {
		return ""
	}

	entityCount, _ := overview["entity_count"].(int)
	languageCounts, _ := overview["language_counts"].(map[string]int)
	signalCounts, _ := overview["signal_counts"].(map[string]int)
	surfaceKindCounts, _ := overview["surface_kind_counts"].(map[string]int)
	if entityCount == 0 || (len(signalCounts) == 0 && len(surfaceKindCounts) == 0) {
		return ""
	}

	fragments := make([]string, 0, len(signalCounts)+len(surfaceKindCounts))
	for _, key := range sortedIntMapKeys(signalCounts) {
		fragments = append(fragments, fmt.Sprintf("%s=%d", key, signalCounts[key]))
	}
	for _, key := range sortedIntMapKeys(surfaceKindCounts) {
		fragments = append(fragments, fmt.Sprintf("%s=%d", key, surfaceKindCounts[key]))
	}

	return fmt.Sprintf(
		"Semantic signals cover %d entity(ies) across %d language(s): %s.",
		entityCount,
		len(languageCounts),
		joinSentenceFragments(fragments),
	)
}

func sortedIntMapKeys(values map[string]int) []string {
	if len(values) == 0 {
		return nil
	}

	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	slices.SortFunc(keys, func(left, right string) int {
		return cmp.Compare(left, right)
	})
	return keys
}

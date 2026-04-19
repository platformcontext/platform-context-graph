package query

import (
	"context"
	"fmt"
	"sort"
	"strings"
)

type provisioningRepositoryCandidate struct {
	RepoID              string
	RepoName            string
	RelationshipTypes   []string
	RelationshipReasons []string
}

type traceEvidenceAccumulator struct {
	samplePaths   map[string]struct{}
	evidenceKinds map[string]struct{}
	modules       map[string]struct{}
	configPaths   map[string]struct{}
	matchedValues map[string]struct{}
}

func loadProvisioningSourceChains(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	serviceRepoID string,
) ([]map[string]any, error) {
	return loadProvisioningSourceChainsWithLimit(ctx, graph, content, serviceRepoID, 0)
}

func loadProvisioningSourceChainsWithLimit(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	serviceRepoID string,
	limit int,
) ([]map[string]any, error) {
	candidates, err := queryProvisioningRepositoryCandidates(ctx, graph, serviceRepoID, limit)
	if err != nil {
		return nil, err
	}
	if len(candidates) == 0 || content == nil {
		return nil, nil
	}

	chains := make([]map[string]any, 0, len(candidates))
	for _, candidate := range candidates {
		entities, err := content.ListRepoEntities(ctx, candidate.RepoID, repositorySemanticEntityLimit)
		if err != nil {
			return nil, fmt.Errorf("list provisioning entities for %q: %w", candidate.RepoID, err)
		}
		evidence := collectProvisioningChainEvidence(entities)
		entry := map[string]any{
			"repository":         candidate.RepoName,
			"repo_id":            candidate.RepoID,
			"relationship_types": candidate.RelationshipTypes,
		}
		if len(candidate.RelationshipReasons) > 0 {
			entry["relationship_reasons"] = candidate.RelationshipReasons
			for _, reason := range candidate.RelationshipReasons {
				evidence.evidenceKinds[reason] = struct{}{}
			}
		}
		if values := sortedAccumulatorValues(evidence.evidenceKinds); len(values) > 0 {
			entry["evidence_kinds"] = values
		}
		if values := sortedAccumulatorValues(evidence.samplePaths); len(values) > 0 {
			entry["sample_paths"] = values
		}
		if values := sortedAccumulatorValues(evidence.modules); len(values) > 0 {
			entry["modules"] = values
		}
		if values := sortedAccumulatorValues(evidence.configPaths); len(values) > 0 {
			entry["config_paths"] = values
		}
		chains = append(chains, entry)
	}

	sort.Slice(chains, func(i, j int) bool {
		return StringVal(chains[i], "repository") < StringVal(chains[j], "repository")
	})
	return chains, nil
}

func loadConsumerRepositoryEnrichment(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	serviceRepoID string,
	serviceName string,
	hostnames []string,
) ([]map[string]any, error) {
	return loadConsumerRepositoryEnrichmentWithLimit(ctx, graph, content, serviceRepoID, serviceName, hostnames, 0)
}

func loadConsumerRepositoryEnrichmentWithLimit(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	serviceRepoID string,
	serviceName string,
	hostnames []string,
	limit int,
) ([]map[string]any, error) {
	candidates, err := queryProvisioningRepositoryCandidates(ctx, graph, serviceRepoID, limit)
	if err != nil {
		return nil, err
	}

	trimmedHostnames := normalizedIndirectEvidenceHostnames(hostnames)
	if limit > 0 {
		trimmedHostnames = boundedIndirectEvidenceHostnames(trimmedHostnames)
		if len(trimmedHostnames) > limit {
			trimmedHostnames = trimmedHostnames[:limit]
		}
	}

	consumersByRepo := make(map[string]map[string]any, len(candidates))
	for _, candidate := range candidates {
		entry := map[string]any{
			"repository":               candidate.RepoName,
			"repo_id":                  candidate.RepoID,
			"consumer_kinds":           []string{"graph_provisioning_consumer"},
			"graph_relationship_types": candidate.RelationshipTypes,
		}
		if len(candidate.RelationshipReasons) > 0 {
			entry["graph_relationship_reasons"] = candidate.RelationshipReasons
		}
		consumersByRepo[candidate.RepoID] = entry
	}

	if content != nil {
		contentEvidence, err := searchConsumerEvidenceAnyRepo(ctx, content, serviceRepoID, serviceName, trimmedHostnames, limit)
		if err != nil {
			return nil, err
		}
		for repoID, evidence := range contentEvidence {
			entry, ok := consumersByRepo[repoID]
			if !ok {
				entry = map[string]any{
					"repo_id":        repoID,
					"repository":     repoID,
					"consumer_kinds": []string{},
				}
				consumersByRepo[repoID] = entry
			}
			appendConsumerEvidence(entry, evidence)
		}
	}

	consumers := make([]map[string]any, 0, len(consumersByRepo))
	for _, entry := range consumersByRepo {
		consumers = append(consumers, entry)
	}

	sort.Slice(consumers, func(i, j int) bool {
		return StringVal(consumers[i], "repository") < StringVal(consumers[j], "repository")
	})
	return consumers, nil
}

func queryProvisioningRepositoryCandidates(
	ctx context.Context,
	graph GraphReader,
	serviceRepoID string,
	limit int,
) ([]provisioningRepositoryCandidate, error) {
	if graph == nil || strings.TrimSpace(serviceRepoID) == "" {
		return nil, nil
	}

	query := `
		MATCH (target:Repository {id: $repo_id})<-[rel:PROVISIONS_DEPENDENCY_FOR|DEPLOYS_FROM|USES_MODULE|DISCOVERS_CONFIG_IN]-(repo:Repository)
		RETURN repo.id AS repo_id,
		       repo.name AS repo_name,
		       type(rel) AS relationship_type,
		       coalesce(rel.reason, rel.evidence_type, '') AS relationship_reason
		ORDER BY repo.name, relationship_type
	`
	params := map[string]any{"repo_id": serviceRepoID}
	if limit > 0 {
		query += " LIMIT $limit"
		params["limit"] = limit
	}
	rows, err := graph.Run(ctx, query, params)
	if err != nil {
		return nil, fmt.Errorf("query provisioning repository candidates: %w", err)
	}

	grouped := make(map[string]*provisioningRepositoryCandidate, len(rows))
	for _, row := range rows {
		repoID := strings.TrimSpace(StringVal(row, "repo_id"))
		repoName := strings.TrimSpace(StringVal(row, "repo_name"))
		if repoID == "" || repoName == "" {
			continue
		}
		candidate, ok := grouped[repoID]
		if !ok {
			candidate = &provisioningRepositoryCandidate{
				RepoID:              repoID,
				RepoName:            repoName,
				RelationshipTypes:   []string{},
				RelationshipReasons: []string{},
			}
			grouped[repoID] = candidate
		}
		appendUniqueString(&candidate.RelationshipTypes, StringVal(row, "relationship_type"))
		appendUniqueString(&candidate.RelationshipReasons, StringVal(row, "relationship_reason"))
	}

	candidates := make([]provisioningRepositoryCandidate, 0, len(grouped))
	for _, candidate := range grouped {
		sort.Strings(candidate.RelationshipTypes)
		sort.Strings(candidate.RelationshipReasons)
		candidates = append(candidates, *candidate)
	}
	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].RepoName < candidates[j].RepoName
	})
	return candidates, nil
}

func collectProvisioningChainEvidence(entities []EntityContent) traceEvidenceAccumulator {
	evidence := newTraceEvidenceAccumulator()
	for _, entity := range entities {
		switch entity.EntityType {
		case "TerraformModule", "TerragruntConfig", "TerragruntDependency":
		default:
			continue
		}
		evidence.samplePaths[entity.RelativePath] = struct{}{}
		relationships, handled, err := buildOutgoingTerraformRelationships(entity)
		if err != nil || !handled {
			continue
		}
		for _, relationship := range relationships {
			if reason := strings.TrimSpace(StringVal(relationship, "reason")); reason != "" {
				evidence.evidenceKinds[reason] = struct{}{}
			}
			targetName := strings.TrimSpace(StringVal(relationship, "target_name"))
			switch StringVal(relationship, "type") {
			case "USES_MODULE":
				if targetName != "" {
					evidence.modules[targetName] = struct{}{}
				}
			case "DISCOVERS_CONFIG_IN":
				if targetName != "" {
					evidence.configPaths[targetName] = struct{}{}
				}
			}
		}
	}
	return evidence
}

func searchConsumerEvidenceAnyRepo(
	ctx context.Context,
	content *ContentReader,
	serviceRepoID string,
	serviceName string,
	hostnames []string,
	limit int,
) (map[string]traceEvidenceAccumulator, error) {
	evidenceByRepo := map[string]traceEvidenceAccumulator{}
	if content == nil {
		return evidenceByRepo, nil
	}
	if limit <= 0 {
		limit = 100
	}

	if serviceName = strings.TrimSpace(serviceName); serviceName != "" {
		rows, err := content.SearchFileContentAnyRepo(ctx, serviceName, limit)
		if err != nil {
			return evidenceByRepo, fmt.Errorf("search consumer evidence for service name: %w", err)
		}
		collectSearchRowsByRepo(evidenceByRepo, rows, serviceRepoID, "repository_reference", serviceName)
	}
	for _, hostname := range hostnames {
		rows, err := content.SearchFileContentAnyRepo(ctx, hostname, limit)
		if err != nil {
			return evidenceByRepo, fmt.Errorf("search consumer evidence for hostname %q: %w", hostname, err)
		}
		collectSearchRowsByRepo(evidenceByRepo, rows, serviceRepoID, "hostname_reference", hostname)
	}
	return evidenceByRepo, nil
}

func collectSearchRowsByRepo(
	evidenceByRepo map[string]traceEvidenceAccumulator,
	rows []FileContent,
	serviceRepoID string,
	evidenceKind string,
	matchedValue string,
) {
	if len(rows) == 0 {
		return
	}
	for _, row := range rows {
		repoID := strings.TrimSpace(row.RepoID)
		if repoID == "" || repoID == strings.TrimSpace(serviceRepoID) {
			continue
		}
		evidence, ok := evidenceByRepo[repoID]
		if !ok {
			evidence = newTraceEvidenceAccumulator()
		}
		evidence.evidenceKinds[evidenceKind] = struct{}{}
		if matchedValue != "" {
			evidence.matchedValues[matchedValue] = struct{}{}
		}
		if relativePath := strings.TrimSpace(row.RelativePath); relativePath != "" {
			evidence.samplePaths[relativePath] = struct{}{}
		}
		evidenceByRepo[repoID] = evidence
	}
}

func appendConsumerEvidence(entry map[string]any, evidence traceEvidenceAccumulator) {
	evidenceKinds := sortedAccumulatorValues(evidence.evidenceKinds)
	if len(evidenceKinds) > 0 {
		entry["evidence_kinds"] = evidenceKinds
	}
	matchedValues := sortedAccumulatorValues(evidence.matchedValues)
	if len(matchedValues) > 0 {
		entry["matched_values"] = matchedValues
	}
	samplePaths := sortedAccumulatorValues(evidence.samplePaths)
	if len(samplePaths) > 0 {
		entry["sample_paths"] = samplePaths
	}

	consumerKinds := StringSliceVal(entry, "consumer_kinds")
	if containsString(evidenceKinds, "repository_reference") {
		appendUniqueString(&consumerKinds, "service_reference_consumer")
	}
	if containsString(evidenceKinds, "hostname_reference") {
		appendUniqueString(&consumerKinds, "hostname_reference_consumer")
	}
	sort.Strings(consumerKinds)
	entry["consumer_kinds"] = consumerKinds
}

func newTraceEvidenceAccumulator() traceEvidenceAccumulator {
	return traceEvidenceAccumulator{
		samplePaths:   map[string]struct{}{},
		evidenceKinds: map[string]struct{}{},
		modules:       map[string]struct{}{},
		configPaths:   map[string]struct{}{},
		matchedValues: map[string]struct{}{},
	}
}

func sortedAccumulatorValues(values map[string]struct{}) []string {
	if len(values) == 0 {
		return nil
	}
	items := make([]string, 0, len(values))
	for value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			items = append(items, trimmed)
		}
	}
	sort.Strings(items)
	return items
}

func appendUniqueString(values *[]string, candidate string) {
	if candidate = strings.TrimSpace(candidate); candidate == "" {
		return
	}
	for _, existing := range *values {
		if existing == candidate {
			return
		}
	}
	*values = append(*values, candidate)
}

func containsString(values []string, candidate string) bool {
	for _, value := range values {
		if value == candidate {
			return true
		}
	}
	return false
}

func boundedTraceEnrichmentLimit(maxDepth int) int {
	if maxDepth <= 0 {
		return 0
	}
	limit := maxDepth * 10
	if limit > 100 {
		return 100
	}
	return limit
}

func normalizedIndirectEvidenceHostnames(hostnames []string) []string {
	if len(hostnames) == 0 {
		return nil
	}
	seen := map[string]struct{}{}
	normalized := make([]string, 0, len(hostnames))
	for _, hostname := range hostnames {
		hostname = strings.TrimSpace(hostname)
		if hostname == "" {
			continue
		}
		if _, ok := seen[hostname]; ok {
			continue
		}
		seen[hostname] = struct{}{}
		normalized = append(normalized, hostname)
	}
	sort.Strings(normalized)
	return normalized
}

func buildStorySections(platforms, platformKinds, environments []string) []map[string]any {
	sections := []map[string]any{
		{
			"title":   "deployment",
			"summary": fmt.Sprintf("%d platform target(s) across %d environment(s)", len(platforms), len(environments)),
		},
	}
	if len(platformKinds) > 0 {
		sections = append(sections, map[string]any{
			"title":   "controllers",
			"summary": fmt.Sprintf("Observed controller families: %s", joinOrNone(platformKinds)),
		})
	}
	return sections
}

func buildGitOpsOverview(platforms, platformKinds []string) map[string]any {
	enabled := false
	for _, kind := range platformKinds {
		if kind == "argocd_application" || kind == "argocd_applicationset" {
			enabled = true
			break
		}
	}
	return map[string]any{
		"enabled":          enabled,
		"tool_families":    platformKinds,
		"observed_targets": platforms,
	}
}

func buildRuntimeOverview(environments []string) map[string]any {
	return map[string]any{
		"environment_count": len(environments),
		"environments":      environments,
	}
}

func buildDeploymentFacts(
	platforms []string,
	platformKinds []string,
	environments []string,
	deploymentSources []map[string]any,
) []map[string]any {
	facts := make([]map[string]any, 0, len(platforms)+len(environments)+len(deploymentSources))
	for i, platform := range platforms {
		fact := map[string]any{
			"type":       "RUNS_ON_PLATFORM",
			"target":     platform,
			"confidence": 1.0,
		}
		if i < len(platformKinds) {
			fact["kind"] = platformKinds[i]
		}
		facts = append(facts, fact)
	}
	for _, environment := range environments {
		facts = append(facts, map[string]any{
			"type":       "OBSERVED_IN_ENVIRONMENT",
			"target":     environment,
			"confidence": 1.0,
		})
	}
	for _, source := range deploymentSources {
		facts = append(facts, map[string]any{
			"type":       "DEPLOYS_FROM",
			"target":     safeStr(source, "repo_name"),
			"target_id":  safeStr(source, "repo_id"),
			"confidence": floatVal(source, "confidence"),
			"reason":     safeStr(source, "reason"),
		})
	}
	return facts
}

func buildControllerDrivenPaths(platforms, platformKinds []string) []map[string]any {
	paths := make([]map[string]any, 0, len(platforms))
	for i, platform := range platforms {
		path := map[string]any{
			"controller": platform,
		}
		if i < len(platformKinds) && platformKinds[i] != "" {
			path["controller_kind"] = platformKinds[i]
		}
		paths = append(paths, path)
	}
	return paths
}

package query

import (
	"context"
	"fmt"
	"sort"
	"strings"
)

func enrichServiceQueryContext(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	workloadContext map[string]any,
) error {
	if len(workloadContext) == 0 || content == nil {
		return nil
	}

	repoID := safeStr(workloadContext, "repo_id")
	serviceName := safeStr(workloadContext, "name")
	if repoID == "" || serviceName == "" {
		return nil
	}

	evidence, err := loadServiceQueryEvidence(ctx, content, repoID, serviceName)
	if err != nil {
		return fmt.Errorf("load service query evidence: %w", err)
	}

	if hostnames := buildServiceHostnameRows(evidence.Hostnames); len(hostnames) > 0 {
		workloadContext["hostnames"] = hostnames
	}

	instanceEnvironments, _ := workloadContext["instances"].([]map[string]any)
	observedEnvironments := mergeStringSets(
		distinctSortedInstanceField(instanceEnvironments, "environment"),
		serviceEvidenceEnvironmentNames(evidence.Environments),
	)
	if len(observedEnvironments) > 0 {
		workloadContext["observed_config_environments"] = observedEnvironments
	}

	if apiSurface := buildServiceAPISurface(evidence); len(apiSurface) > 0 {
		workloadContext["api_surface"] = apiSurface
	}

	if graph != nil {
		hostnames := serviceEvidenceHostnames(evidence)
		consumers, err := loadConsumerRepositoryEnrichment(ctx, graph, content, repoID, serviceName, hostnames)
		if err != nil {
			return fmt.Errorf("load consumer repository enrichment: %w", err)
		}
		if len(consumers) > 0 {
			workloadContext["consumer_repositories"] = consumers
		}

		provisioningChains, err := loadProvisioningSourceChains(ctx, graph, content, repoID)
		if err != nil {
			return fmt.Errorf("load provisioning source chains: %w", err)
		}
		if len(provisioningChains) > 0 {
			workloadContext["provisioning_source_chains"] = provisioningChains
		}
	}

	if documentationOverview := buildServiceDocumentationOverview(ctx, graph, workloadContext, evidence); len(documentationOverview) > 0 {
		workloadContext["documentation_overview"] = documentationOverview
	}
	if supportOverview := buildServiceSupportOverview(workloadContext); len(supportOverview) > 0 {
		workloadContext["support_overview"] = supportOverview
	}
	workloadContext["deployment_overview"] = buildServiceDeploymentOverview(workloadContext)
	workloadContext["story_sections"] = buildServiceStorySections(workloadContext)

	return nil
}

func buildServiceStoryResponse(serviceName string, workloadContext map[string]any) map[string]any {
	response := map[string]any{
		"service_name":        serviceName,
		"story":               buildWorkloadStory(workloadContext),
		"story_sections":      buildServiceStorySections(workloadContext),
		"deployment_overview": buildServiceDeploymentOverview(workloadContext),
	}
	for _, key := range []string{
		"documentation_overview",
		"support_overview",
		"hostnames",
		"observed_config_environments",
		"api_surface",
		"consumer_repositories",
		"provisioning_source_chains",
	} {
		if value, ok := workloadContext[key]; ok && value != nil {
			response[key] = value
		}
	}
	return response
}

func buildServiceDeploymentOverview(workloadContext map[string]any) map[string]any {
	instances, _ := workloadContext["instances"].([]map[string]any)
	platforms := distinctSortedInstanceField(instances, "platform_name")
	observedEnvironments := mergeStringSets(
		distinctSortedInstanceField(instances, "environment"),
		StringSliceVal(workloadContext, "observed_config_environments"),
	)

	overview := map[string]any{
		"instance_count":    len(instances),
		"environment_count": len(observedEnvironments),
		"platform_count":    len(platforms),
		"platforms":         platforms,
		"environments":      observedEnvironments,
	}
	if hostnames := mapSliceValue(workloadContext, "hostnames"); len(hostnames) > 0 {
		overview["hostname_count"] = len(hostnames)
		overview["hostnames"] = hostnames
	}
	if apiSurface := mapValue(workloadContext, "api_surface"); len(apiSurface) > 0 {
		overview["api_surface"] = apiSurface
	}
	if consumers := mapSliceValue(workloadContext, "consumer_repositories"); len(consumers) > 0 {
		overview["consumer_repository_count"] = len(consumers)
	}
	if provisioningChains := mapSliceValue(workloadContext, "provisioning_source_chains"); len(provisioningChains) > 0 {
		overview["provisioning_source_chain_count"] = len(provisioningChains)
	}
	return overview
}

func buildServiceStorySections(workloadContext map[string]any) []map[string]any {
	overview := buildServiceDeploymentOverview(workloadContext)
	sections := []map[string]any{
		{
			"title": "deployment",
			"summary": fmt.Sprintf(
				"%d instance(s), %d environment signal(s), %d platform target(s)",
				IntVal(overview, "instance_count"),
				IntVal(overview, "environment_count"),
				IntVal(overview, "platform_count"),
			),
		},
	}

	if hostnames := mapSliceValue(workloadContext, "hostnames"); len(hostnames) > 0 {
		sections = append(sections, map[string]any{
			"title":   "entrypoints",
			"summary": fmt.Sprintf("%d observed hostname entrypoint(s)", len(hostnames)),
		})
	}
	if apiSurface := mapValue(workloadContext, "api_surface"); len(apiSurface) > 0 {
		sections = append(sections, map[string]any{
			"title": "api",
			"summary": fmt.Sprintf(
				"%d endpoint(s), %d method(s), %d spec file(s)",
				IntVal(apiSurface, "endpoint_count"),
				IntVal(apiSurface, "method_count"),
				IntVal(apiSurface, "spec_count"),
			),
		})
	}
	if consumers := mapSliceValue(workloadContext, "consumer_repositories"); len(consumers) > 0 {
		sections = append(sections, map[string]any{
			"title":   "consumers",
			"summary": fmt.Sprintf("%d consumer repo(s) observed from graph and content evidence", len(consumers)),
		})
	}
	if provisioningChains := mapSliceValue(workloadContext, "provisioning_source_chains"); len(provisioningChains) > 0 {
		sections = append(sections, map[string]any{
			"title":   "provisioning",
			"summary": fmt.Sprintf("%d provisioning source chain(s) observed", len(provisioningChains)),
		})
	}
	return sections
}

func buildServiceDocumentationOverview(
	ctx context.Context,
	graph GraphReader,
	workloadContext map[string]any,
	evidence ServiceQueryEvidence,
) map[string]any {
	repoID := safeStr(workloadContext, "repo_id")
	repoName := safeStr(workloadContext, "repo_name")
	if repoID == "" && repoName == "" {
		return nil
	}

	overview := map[string]any{
		"repo_id":               repoID,
		"repo_name":             repoName,
		"portable_identifier":   repoID,
		"docs_route_count":      len(evidence.DocsRoutes),
		"api_spec_count":        len(evidence.APISpecs),
		"entrypoint_host_count": len(buildServiceHostnameRows(evidence.Hostnames)),
	}

	if graph != nil && repoID != "" {
		row, err := graph.RunSingle(ctx, fmt.Sprintf(
			`MATCH (r:Repository {id: $repo_id}) RETURN %s`,
			RepoProjection("r"),
		), map[string]any{"repo_id": repoID})
		if err == nil && row != nil {
			repo := RepoRefFromRow(row)
			overview["remote_url"] = repo.RemoteURL
			overview["repo_slug"] = repo.RepoSlug
			overview["has_remote"] = repo.HasRemote
			overview["local_path_present"] = repo.LocalPath != ""
		}
	}

	specPaths := make([]string, 0, len(evidence.APISpecs))
	for _, spec := range evidence.APISpecs {
		specPaths = append(specPaths, spec.RelativePath)
	}
	sort.Strings(specPaths)
	if len(specPaths) > 0 {
		overview["api_spec_paths"] = specPaths
	}
	return overview
}

func buildServiceSupportOverview(workloadContext map[string]any) map[string]any {
	overview := map[string]any{
		"dependency_count":           len(mapSliceValue(workloadContext, "dependencies")),
		"consumer_repository_count":  len(mapSliceValue(workloadContext, "consumer_repositories")),
		"provisioning_source_count":  len(mapSliceValue(workloadContext, "provisioning_source_chains")),
		"observed_environment_count": len(StringSliceVal(workloadContext, "observed_config_environments")),
		"entrypoint_host_count":      len(mapSliceValue(workloadContext, "hostnames")),
		"has_api_surface":            len(mapValue(workloadContext, "api_surface")) > 0,
		"has_documentation_overview": len(mapValue(workloadContext, "documentation_overview")) > 0,
	}
	if apiSurface := mapValue(workloadContext, "api_surface"); len(apiSurface) > 0 {
		overview["endpoint_count"] = IntVal(apiSurface, "endpoint_count")
		overview["method_count"] = IntVal(apiSurface, "method_count")
		overview["spec_count"] = IntVal(apiSurface, "spec_count")
	}
	return overview
}

func buildServiceHostnameRows(rows []ServiceHostnameEvidence) []map[string]any {
	if len(rows) == 0 {
		return nil
	}
	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		result = append(result, map[string]any{
			"hostname":      row.Hostname,
			"environment":   row.Environment,
			"relative_path": row.RelativePath,
			"reason":        row.Reason,
		})
	}
	return result
}

func hostnameLabels(rows []map[string]any) []string {
	if len(rows) == 0 {
		return nil
	}
	values := make([]string, 0, len(rows))
	for _, row := range rows {
		hostname := StringVal(row, "hostname")
		if hostname == "" {
			continue
		}
		values = append(values, hostname)
	}
	return uniqueSortedStrings(values)
}

func buildServiceAPISurface(evidence ServiceQueryEvidence) map[string]any {
	if len(evidence.APISpecs) == 0 && len(evidence.DocsRoutes) == 0 {
		return nil
	}

	docsRoutes := serviceEvidenceDocsRoutes(evidence)
	hostnames := serviceEvidenceHostnames(evidence)
	specPaths := make([]string, 0, len(evidence.APISpecs))
	specVersions := make([]string, 0, len(evidence.APISpecs))
	apiVersions := make([]string, 0, len(evidence.APISpecs))
	endpointCount := 0
	methodCount := 0
	operationIDCount := 0
	parsedSpecCount := 0
	for _, spec := range evidence.APISpecs {
		specPaths = append(specPaths, spec.RelativePath)
		endpointCount += spec.EndpointCount
		methodCount += spec.MethodCount
		operationIDCount += spec.OperationIDCount
		if spec.Parsed {
			parsedSpecCount++
		}
		if spec.SpecVersion != "" {
			specVersions = append(specVersions, spec.SpecVersion)
		}
		if spec.APIVersion != "" {
			apiVersions = append(apiVersions, spec.APIVersion)
		}
	}
	sort.Strings(specPaths)

	return map[string]any{
		"spec_count":         len(evidence.APISpecs),
		"parsed_spec_count":  parsedSpecCount,
		"spec_paths":         uniqueSortedStrings(specPaths),
		"spec_versions":      uniqueSortedStrings(specVersions),
		"api_versions":       uniqueSortedStrings(apiVersions),
		"endpoint_count":     endpointCount,
		"method_count":       methodCount,
		"operation_id_count": operationIDCount,
		"docs_routes":        docsRoutes,
		"hostnames":          hostnames,
	}
}

func serviceEvidenceHostnames(evidence ServiceQueryEvidence) []string {
	values := make([]string, 0, len(evidence.Hostnames)+len(evidence.APISpecs))
	for _, row := range evidence.Hostnames {
		values = append(values, row.Hostname)
	}
	for _, spec := range evidence.APISpecs {
		values = append(values, spec.Hostnames...)
	}
	return uniqueSortedStrings(values)
}

func serviceEvidenceDocsRoutes(evidence ServiceQueryEvidence) []string {
	values := make([]string, 0, len(evidence.DocsRoutes)+len(evidence.APISpecs))
	for _, row := range evidence.DocsRoutes {
		values = append(values, row.Route)
	}
	for _, spec := range evidence.APISpecs {
		values = append(values, spec.DocsRoutes...)
	}
	return uniqueSortedStrings(values)
}

func serviceEvidenceEnvironmentNames(rows []ServiceEnvironmentEvidence) []string {
	values := make([]string, 0, len(rows))
	for _, row := range rows {
		values = append(values, row.Environment)
	}
	return uniqueSortedStrings(values)
}

func uniqueSortedStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

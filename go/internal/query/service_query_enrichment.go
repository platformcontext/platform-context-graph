package query

import (
	"context"
	"fmt"
	"sort"
	"strings"
)

type serviceQueryEnrichmentOptions struct {
	DirectOnly                bool
	IncludeRelatedModuleUsage bool
	MaxDepth                  int
}

func enrichServiceQueryContext(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	workloadContext map[string]any,
) error {
	return enrichServiceQueryContextWithOptions(ctx, graph, content, workloadContext, serviceQueryEnrichmentOptions{
		IncludeRelatedModuleUsage: true,
	})
}

func enrichServiceQueryContextWithOptions(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	workloadContext map[string]any,
	opts serviceQueryEnrichmentOptions,
) error {
	delete(workloadContext, "entry_points")
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

	// Load framework-detected routes from fact_records when ContentReader
	// is available (it has access to the same Postgres database).
	if content != nil {
		frameworkRoutes, err := content.ListFrameworkRoutes(ctx, repoID)
		if err != nil {
			return fmt.Errorf("load framework routes: %w", err)
		}
		evidence.FrameworkRoutes = frameworkRoutes
	}

	if hostnames := buildServiceHostnameRows(evidence.Hostnames); len(hostnames) > 0 {
		workloadContext["hostnames"] = hostnames
	}
	if entrypoints := buildServiceEntrypoints(workloadContext, evidence); len(entrypoints) > 0 {
		workloadContext["entrypoints"] = entrypoints
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
	if networkPaths := buildServiceNetworkPaths(workloadContext, mapSliceValue(workloadContext, "entrypoints")); len(networkPaths) > 0 {
		workloadContext["network_paths"] = networkPaths
	}

	if graph != nil {
		hostnames := serviceEvidenceHostnames(evidence)
		traceLimit := boundedTraceEnrichmentLimit(opts.MaxDepth)
		if !opts.DirectOnly {
			dependentCandidates, err := queryProvisioningRepositoryCandidates(ctx, graph, repoID, traceLimit)
			if err != nil {
				return fmt.Errorf("load graph dependents: %w", err)
			}
			if dependents := buildGraphDependents(dependentCandidates); len(dependents) > 0 {
				workloadContext["dependents"] = dependents
			}

			consumers, err := loadConsumerRepositoryEnrichmentWithLimit(ctx, graph, content, repoID, serviceName, hostnames, traceLimit)
			if err != nil {
				return fmt.Errorf("load consumer repository enrichment: %w", err)
			}
			if len(consumers) > 0 {
				workloadContext["consumer_repositories"] = consumers
			}
		}

		if opts.IncludeRelatedModuleUsage {
			provisioningChains, err := loadProvisioningSourceChainsWithLimit(ctx, graph, content, repoID, traceLimit)
			if err != nil {
				return fmt.Errorf("load provisioning source chains: %w", err)
			}
			if len(provisioningChains) > 0 {
				workloadContext["provisioning_source_chains"] = provisioningChains
			}
		}
	}

	if documentationOverview := buildServiceDocumentationOverview(ctx, graph, workloadContext, evidence); len(documentationOverview) > 0 {
		workloadContext["documentation_overview"] = documentationOverview
	}
	deploymentEvidence, err := loadServiceDeploymentEvidence(ctx, graph, content, workloadContext)
	if err != nil {
		return fmt.Errorf("load service deployment evidence: %w", err)
	}
	if len(deploymentEvidence) > 0 {
		workloadContext["deployment_evidence"] = deploymentEvidence
	}
	if supportOverview := buildServiceSupportOverview(workloadContext); len(supportOverview) > 0 {
		workloadContext["support_overview"] = supportOverview
	}
	workloadContext["deployment_overview"] = buildServiceDeploymentOverview(workloadContext)
	workloadContext["story_sections"] = buildServiceStorySections(workloadContext)

	return nil
}

func buildServiceStoryResponse(serviceName string, workloadContext map[string]any) map[string]any {
	serviceName = canonicalServiceName(serviceName, workloadContext)
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
		"entrypoints",
		"network_paths",
		"dependents",
		"observed_config_environments",
		"api_surface",
		"consumer_repositories",
		"provisioning_source_chains",
		"deployment_evidence",
	} {
		if value, ok := workloadContext[key]; ok && value != nil {
			response[key] = value
		}
	}
	return response
}

func canonicalServiceName(requestedServiceName string, workloadContext map[string]any) string {
	if canonicalName := safeStr(workloadContext, "name"); canonicalName != "" {
		return canonicalName
	}
	return strings.TrimSpace(requestedServiceName)
}

func buildServiceDeploymentOverview(workloadContext map[string]any) map[string]any {
	instances, _ := workloadContext["instances"].([]map[string]any)
	platforms := distinctSortedInstanceField(instances, "platform_name")
	materializedEnvironments := distinctSortedInstanceField(instances, "environment")
	configEnvironments := StringSliceVal(workloadContext, "observed_config_environments")

	overview := map[string]any{
		"instance_count":                 len(instances),
		"environment_count":              len(materializedEnvironments),
		"materialized_environment_count": len(materializedEnvironments),
		"config_environment_count":       len(configEnvironments),
		"platform_count":                 len(platforms),
		"platforms":                      platforms,
		"environments":                   materializedEnvironments,
		"materialized_environments":      materializedEnvironments,
	}
	if len(configEnvironments) > 0 {
		overview["config_environments"] = configEnvironments
	}
	if hostnames := mapSliceValue(workloadContext, "hostnames"); len(hostnames) > 0 {
		overview["hostname_count"] = len(hostnames)
		overview["hostnames"] = hostnames
	}
	if entrypoints := mapSliceValue(workloadContext, "entrypoints"); len(entrypoints) > 0 {
		overview["entrypoint_count"] = len(entrypoints)
		overview["entrypoints"] = entrypoints
	}
	if networkPaths := mapSliceValue(workloadContext, "network_paths"); len(networkPaths) > 0 {
		overview["network_path_count"] = len(networkPaths)
	}
	if apiSurface := mapValue(workloadContext, "api_surface"); len(apiSurface) > 0 {
		overview["api_surface"] = apiSurface
	}
	if dependents := mapSliceValue(workloadContext, "dependents"); len(dependents) > 0 {
		overview["dependent_count"] = len(dependents)
	}
	if consumers := mapSliceValue(workloadContext, "consumer_repositories"); len(consumers) > 0 {
		overview["consumer_repository_count"] = len(consumers)
	}
	if provisioningChains := mapSliceValue(workloadContext, "provisioning_source_chains"); len(provisioningChains) > 0 {
		overview["provisioning_source_chain_count"] = len(provisioningChains)
	}
	if deploymentEvidence := mapValue(workloadContext, "deployment_evidence"); len(deploymentEvidence) > 0 {
		if toolFamilies := stringSliceValue(deploymentEvidence, "tool_families"); len(toolFamilies) > 0 {
			overview["deployment_tool_families"] = toolFamilies
		}
		if deliveryPaths := mapSliceValue(deploymentEvidence, "delivery_paths"); len(deliveryPaths) > 0 {
			overview["delivery_path_count"] = len(deliveryPaths)
		}
		if deliveryWorkflows := mapSliceValue(deploymentEvidence, "delivery_workflows"); len(deliveryWorkflows) > 0 {
			overview["delivery_workflow_count"] = len(deliveryWorkflows)
		}
		if sharedConfigPaths := mapSliceValue(deploymentEvidence, "shared_config_paths"); len(sharedConfigPaths) > 0 {
			overview["shared_config_path_count"] = len(sharedConfigPaths)
		}
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
	if networkPaths := mapSliceValue(workloadContext, "network_paths"); len(networkPaths) > 0 {
		sections = append(sections, map[string]any{
			"title":   "network",
			"summary": fmt.Sprintf("%d evidence-backed network path(s) connect entrypoints to runtime targets", len(networkPaths)),
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
	if dependents := mapSliceValue(workloadContext, "dependents"); len(dependents) > 0 {
		sections = append(sections, map[string]any{
			"title":   "dependents",
			"summary": fmt.Sprintf("%d graph-derived dependent repo(s) observed from typed relationships", len(dependents)),
		})
	}
	if provisioningChains := mapSliceValue(workloadContext, "provisioning_source_chains"); len(provisioningChains) > 0 {
		sections = append(sections, map[string]any{
			"title":   "provisioning",
			"summary": fmt.Sprintf("%d provisioning source chain(s) observed", len(provisioningChains)),
		})
	}
	if deploymentEvidence := mapValue(workloadContext, "deployment_evidence"); len(deploymentEvidence) > 0 {
		sections = append(sections, map[string]any{
			"title": "delivery",
			"summary": fmt.Sprintf(
				"%d delivery path(s) across tool families %s",
				len(mapSliceValue(deploymentEvidence, "delivery_paths")),
				joinOrNone(stringSliceValue(deploymentEvidence, "tool_families")),
			),
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
		"dependent_count":            len(mapSliceValue(workloadContext, "dependents")),
		"consumer_repository_count":  len(mapSliceValue(workloadContext, "consumer_repositories")),
		"provisioning_source_count":  len(mapSliceValue(workloadContext, "provisioning_source_chains")),
		"observed_environment_count": len(StringSliceVal(workloadContext, "observed_config_environments")),
		"entrypoint_host_count":      len(mapSliceValue(workloadContext, "hostnames")),
		"entrypoint_count":           len(mapSliceValue(workloadContext, "entrypoints")),
		"network_path_count":         len(mapSliceValue(workloadContext, "network_paths")),
		"has_api_surface":            len(mapValue(workloadContext, "api_surface")) > 0,
		"has_documentation_overview": len(mapValue(workloadContext, "documentation_overview")) > 0,
	}
	if apiSurface := mapValue(workloadContext, "api_surface"); len(apiSurface) > 0 {
		overview["endpoint_count"] = IntVal(apiSurface, "endpoint_count")
		overview["method_count"] = IntVal(apiSurface, "method_count")
		overview["spec_count"] = IntVal(apiSurface, "spec_count")
	}
	if deploymentEvidence := mapValue(workloadContext, "deployment_evidence"); len(deploymentEvidence) > 0 {
		overview["deployment_tool_family_count"] = len(stringSliceValue(deploymentEvidence, "tool_families"))
		overview["delivery_path_count"] = len(mapSliceValue(deploymentEvidence, "delivery_paths"))
		overview["delivery_workflow_count"] = len(mapSliceValue(deploymentEvidence, "delivery_workflows"))
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
	if len(evidence.APISpecs) == 0 && len(evidence.DocsRoutes) == 0 && len(evidence.FrameworkRoutes) == 0 {
		return nil
	}

	docsRoutes := serviceEvidenceDocsRoutes(evidence)
	hostnames := serviceEvidenceHostnames(evidence)
	specPaths := make([]string, 0, len(evidence.APISpecs))
	specVersions := make([]string, 0, len(evidence.APISpecs))
	apiVersions := make([]string, 0, len(evidence.APISpecs))
	endpoints := make([]map[string]any, 0)
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
		for _, endpoint := range spec.Endpoints {
			endpoints = append(endpoints, map[string]any{
				"path":          endpoint.Path,
				"methods":       append([]string(nil), endpoint.Methods...),
				"operation_ids": append([]string(nil), endpoint.OperationIDs...),
				"spec_path":     spec.RelativePath,
			})
		}
	}
	sort.Strings(specPaths)
	sort.Slice(endpoints, func(i, j int) bool {
		if StringVal(endpoints[i], "path") != StringVal(endpoints[j], "path") {
			return StringVal(endpoints[i], "path") < StringVal(endpoints[j], "path")
		}
		return StringVal(endpoints[i], "spec_path") < StringVal(endpoints[j], "spec_path")
	})

	// Merge framework-detected routes into the endpoint list.
	frameworkRouteCount := 0
	frameworkSet := map[string]struct{}{}
	for _, fr := range evidence.FrameworkRoutes {
		frameworkSet[fr.Framework] = struct{}{}
		for _, routePath := range fr.RoutePaths {
			endpoints = append(endpoints, map[string]any{
				"path":      routePath,
				"methods":   lowerStrings(fr.RouteMethods),
				"source":    "framework",
				"framework": fr.Framework,
				"spec_path": fr.RelativePath,
			})
			frameworkRouteCount++
		}
	}
	frameworks := make([]string, 0, len(frameworkSet))
	for fw := range frameworkSet {
		frameworks = append(frameworks, fw)
	}
	sort.Strings(frameworks)

	// Re-sort endpoints after framework routes added.
	sort.Slice(endpoints, func(i, j int) bool {
		if StringVal(endpoints[i], "path") != StringVal(endpoints[j], "path") {
			return StringVal(endpoints[i], "path") < StringVal(endpoints[j], "path")
		}
		return StringVal(endpoints[i], "spec_path") < StringVal(endpoints[j], "spec_path")
	})

	result := map[string]any{
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
		"endpoints":          endpoints,
	}
	if frameworkRouteCount > 0 {
		result["framework_route_count"] = frameworkRouteCount
		result["frameworks"] = frameworks
	}
	return result
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

func lowerStrings(values []string) []string {
	result := make([]string, len(values))
	for i, v := range values {
		result[i] = strings.ToLower(v)
	}
	sort.Strings(result)
	return result
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

package reducer

import (
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

// terraformRepoSignals aggregates Terraform signal data per repository scope.
type terraformRepoSignals struct {
	RepoID        string
	RepoName      string
	ResourceTypes []string
	ResourceNames []string
	ModuleSources []string
	ModuleNames   []string
	DataTypes     []string
	DataNames     []string
}

// ExtractInfrastructurePlatformRows reads fact envelopes, extracts Terraform
// signal data per repository, and returns InfrastructurePlatformRow entries
// for repos where a platform descriptor can be inferred.
//
// This is the content-store-first equivalent of the Python
// materialize_infrastructure_platforms_for_repo_paths Neo4j query.
func ExtractInfrastructurePlatformRows(envelopes []facts.Envelope) []InfrastructurePlatformRow {
	if len(envelopes) == 0 {
		return nil
	}

	// Pass 1: collect repo identity per scope from repository facts.
	repoByScope := make(map[string]*terraformRepoSignals)
	repoByID := make(map[string]*terraformRepoSignals)
	for i := range envelopes {
		env := &envelopes[i]
		if env.FactKind != "repository" {
			continue
		}
		repoID := payloadStr(env.Payload, "repo_id")
		if repoID == "" {
			repoID = payloadStr(env.Payload, "graph_id")
		}
		repoName := payloadStr(env.Payload, "repo_name")
		if repoName == "" {
			repoName = payloadStr(env.Payload, "name")
		}
		if repoID == "" {
			continue
		}
		signals := &terraformRepoSignals{
			RepoID:   repoID,
			RepoName: repoName,
		}
		repoByID[repoID] = signals
		if env.ScopeID != "" {
			repoByScope[env.ScopeID] = signals
		}
	}

	// Pass 2: scan Terraform-bearing file facts for Terraform buckets.
	for i := range envelopes {
		env := &envelopes[i]
		payload, ok := terraformSignalPayload(env)
		if !ok {
			continue
		}
		signals := repoByScope[env.ScopeID]
		if signals == nil {
			signals = repoByID[payloadStr(env.Payload, "repo_id")]
		}
		if signals == nil {
			continue
		}
		extractTerraformResourceSignals(payload, signals)
		extractTerraformModuleSignals(payload, signals)
		extractTerraformDataSourceSignals(payload, signals)
	}

	// Pass 3: infer platform descriptors for repos with Terraform signals.
	var rows []InfrastructurePlatformRow
	for _, signals := range repoByScope {
		if !hasTerraformSignals(signals) {
			continue
		}
		descriptor := InferInfrastructurePlatformDescriptor(InfrastructurePlatformInput{
			DataTypes:     signals.DataTypes,
			DataNames:     signals.DataNames,
			ModuleSources: signals.ModuleSources,
			ModuleNames:   signals.ModuleNames,
			ResourceTypes: signals.ResourceTypes,
			ResourceNames: signals.ResourceNames,
			RepoName:      signals.RepoName,
		})
		if descriptor == nil {
			continue
		}
		rows = append(rows, InfrastructurePlatformRow{
			RepoID:           signals.RepoID,
			PlatformID:       descriptor.PlatformID,
			PlatformName:     descriptor.PlatformName,
			PlatformKind:     descriptor.PlatformKind,
			PlatformProvider: descriptor.PlatformProvider,
			PlatformLocator:  descriptor.PlatformLocator,
		})
	}

	return rows
}

func extractTerraformResourceSignals(payload map[string]any, signals *terraformRepoSignals) {
	resources, ok := payload["terraform_resources"].([]any)
	if !ok {
		return
	}
	for _, item := range resources {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		rt := strings.TrimSpace(strings.ToLower(payloadStr(m, "resource_type")))
		if rt != "" {
			signals.ResourceTypes = append(signals.ResourceTypes, rt)
		}
		if rn := strings.TrimSpace(payloadStr(m, "resource_name")); rn != "" && isPlatformClusterResourceType(rt) {
			signals.ResourceNames = append(signals.ResourceNames, rn)
		}
	}
}

func extractTerraformModuleSignals(payload map[string]any, signals *terraformRepoSignals) {
	modules, ok := payload["terraform_modules"].([]any)
	if !ok {
		return
	}
	for _, item := range modules {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		src := strings.TrimSpace(strings.ToLower(payloadStr(m, "source")))
		if src != "" {
			signals.ModuleSources = append(signals.ModuleSources, src)
		}
		if name := strings.TrimSpace(payloadStr(m, "name")); name != "" && isPlatformClusterModuleSource(src) {
			signals.ModuleNames = append(signals.ModuleNames, name)
		}
	}
}

// isPlatformClusterResourceType reports whether a Terraform resource type is a
// registered platform resource, not merely a sibling service dependency.
func isPlatformClusterResourceType(resourceType string) bool {
	for _, family := range runtimeFamilies {
		for _, clusterType := range family.ClusterResourceTypes {
			if resourceType == clusterType {
				return true
			}
		}
	}
	return false
}

// isPlatformClusterModuleSource reports whether a module source is a registered
// cluster module whose name can safely label a platform.
func isPlatformClusterModuleSource(source string) bool {
	for _, family := range runtimeFamilies {
		for _, pattern := range family.ClusterModulePatterns {
			if strings.Contains(source, pattern) {
				return true
			}
		}
	}
	return false
}

func extractTerraformDataSourceSignals(payload map[string]any, signals *terraformRepoSignals) {
	dataSources, ok := payload["terraform_data_sources"].([]any)
	if !ok {
		return
	}
	for _, item := range dataSources {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if dt := strings.TrimSpace(strings.ToLower(payloadStr(m, "data_type"))); dt != "" {
			signals.DataTypes = append(signals.DataTypes, dt)
		}
		if dn := strings.TrimSpace(payloadStr(m, "data_name")); dn != "" {
			signals.DataNames = append(signals.DataNames, dn)
		}
	}
}

func hasTerraformSignals(signals *terraformRepoSignals) bool {
	return len(signals.ResourceTypes) > 0 ||
		len(signals.ModuleSources) > 0 ||
		len(signals.DataTypes) > 0
}

func terraformSignalPayload(env *facts.Envelope) (map[string]any, bool) {
	switch env.FactKind {
	case "parsed_file_data":
		return env.Payload, true
	case "file":
		payload, ok := env.Payload["parsed_file_data"].(map[string]any)
		return payload, ok
	default:
		return nil, false
	}
}

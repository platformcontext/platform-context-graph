package reducer

import (
	"fmt"
	"regexp"
	"strings"
)

// Evidence source constant for workload finalization.
const EvidenceSourceWorkloads = "finalization/workloads"

var overlayEnvironmentRE = regexp.MustCompile(`(?:^|/)overlays/([^/]+)/`)

// WorkloadCandidate holds one candidate row for workload projection. This is
// the Go equivalent of the Python candidate_rows dict produced by
// _load_candidate_rows.
type WorkloadCandidate struct {
	RepoID           string
	RepoName         string
	ResourceKinds    []string
	Namespaces       []string
	DeploymentRepoID string
}

// ProjectionStats tracks counts produced during projection row building.
type ProjectionStats struct {
	Workloads         int
	Instances         int
	DeploymentSources int
}

// WorkloadRow is one canonical workload upsert payload.
type WorkloadRow struct {
	RepoID       string
	WorkloadID   string
	WorkloadKind string
	WorkloadName string
}

// InstanceRow is one canonical workload instance upsert payload.
type InstanceRow struct {
	Environment  string
	InstanceID   string
	RepoID       string
	WorkloadID   string
	WorkloadKind string
	WorkloadName string
}

// DeploymentSourceRow is one canonical deployment source edge payload.
type DeploymentSourceRow struct {
	DeploymentRepoID string
	Environment      string
	InstanceID       string
	WorkloadName     string
}

// RuntimePlatformRow is one canonical runtime platform upsert payload.
type RuntimePlatformRow struct {
	Environment      string
	InstanceID       string
	PlatformID       string
	PlatformKind     string
	PlatformLocator  string
	PlatformName     string
	PlatformProvider string
	PlatformRegion   string
	RepoID           string
}

// RepoDescriptor maps a repository to its inferred workload identity.
type RepoDescriptor struct {
	RepoID     string
	RepoName   string
	WorkloadID string
}

// ProjectionResult holds all outputs from BuildProjectionRows.
type ProjectionResult struct {
	Stats               ProjectionStats
	WorkloadRows        []WorkloadRow
	InstanceRows        []InstanceRow
	DeploymentSourceRows []DeploymentSourceRow
	RuntimePlatformRows []RuntimePlatformRow
	RepoDescriptors     []RepoDescriptor
}

// InferWorkloadKind infers a workload kind from its name and matched runtime
// resource kinds. Name-based inference takes precedence over resource kinds.
func InferWorkloadKind(name string, resourceKinds []string) string {
	normalized := strings.ToLower(name)
	if strings.Contains(normalized, "cron") {
		return "cronjob"
	}
	if strings.Contains(normalized, "worker") {
		return "worker"
	}
	if strings.Contains(normalized, "consumer") {
		return "consumer"
	}
	if strings.Contains(normalized, "batch") {
		return "batch"
	}
	return "service"
}

// ExtractOverlayEnvironments extracts environment names from repo-relative
// overlay paths using the pattern overlays/<env>/.
func ExtractOverlayEnvironments(paths []string) []string {
	seen := make(map[string]struct{})
	var environments []string
	for _, raw := range paths {
		match := overlayEnvironmentRE.FindStringSubmatch(raw)
		if match == nil {
			continue
		}
		env := strings.TrimSpace(match[1])
		if env == "" {
			continue
		}
		if _, ok := seen[env]; ok {
			continue
		}
		seen[env] = struct{}{}
		environments = append(environments, env)
	}
	return environments
}

// BuildProjectionRows builds batched projection payloads from workload
// candidates. This is the Go equivalent of Python's build_projection_rows.
func BuildProjectionRows(
	candidates []WorkloadCandidate,
	deploymentEnvironments map[string][]string,
) *ProjectionResult {
	result := &ProjectionResult{}
	seenWorkloads := make(map[string]struct{})
	seenInstances := make(map[string]struct{})
	seenDeploymentSources := make(map[string]struct{})
	seenRuntimePlatforms := make(map[string]struct{})

	for _, candidate := range candidates {
		if candidate.RepoID == "" || candidate.RepoName == "" {
			continue
		}
		workloadID := fmt.Sprintf("workload:%s", candidate.RepoName)
		workloadKind := InferWorkloadKind(candidate.RepoName, candidate.ResourceKinds)

		result.RepoDescriptors = append(result.RepoDescriptors, RepoDescriptor{
			RepoID:     candidate.RepoID,
			RepoName:   candidate.RepoName,
			WorkloadID: workloadID,
		})

		if _, ok := seenWorkloads[workloadID]; !ok {
			seenWorkloads[workloadID] = struct{}{}
			result.WorkloadRows = append(result.WorkloadRows, WorkloadRow{
				RepoID:       candidate.RepoID,
				WorkloadID:   workloadID,
				WorkloadKind: workloadKind,
				WorkloadName: candidate.RepoName,
			})
			result.Stats.Workloads++
		}

		// Resolve environments: deployment overlay environments first, then
		// namespace fallback.
		environments := deploymentEnvironments[candidate.DeploymentRepoID]
		if len(environments) == 0 {
			for _, ns := range candidate.Namespaces {
				ns = strings.TrimSpace(ns)
				if ns != "" {
					environments = append(environments, ns)
				}
			}
		}

		platformKind := InferRuntimePlatformKind(candidate.ResourceKinds)

		for _, environment := range environments {
			instanceID := fmt.Sprintf("workload-instance:%s:%s", candidate.RepoName, environment)

			if _, ok := seenInstances[instanceID]; !ok {
				seenInstances[instanceID] = struct{}{}
				result.InstanceRows = append(result.InstanceRows, InstanceRow{
					Environment:  environment,
					InstanceID:   instanceID,
					RepoID:       candidate.RepoID,
					WorkloadID:   workloadID,
					WorkloadKind: workloadKind,
					WorkloadName: candidate.RepoName,
				})
				result.Stats.Instances++
			}

			if candidate.DeploymentRepoID != "" {
				dsKey := instanceID + "|" + candidate.DeploymentRepoID
				if _, ok := seenDeploymentSources[dsKey]; !ok {
					seenDeploymentSources[dsKey] = struct{}{}
					result.DeploymentSourceRows = append(result.DeploymentSourceRows, DeploymentSourceRow{
						DeploymentRepoID: candidate.DeploymentRepoID,
						Environment:      environment,
						InstanceID:       instanceID,
						WorkloadName:     candidate.RepoName,
					})
					result.Stats.DeploymentSources++
				}
			}

			if platformKind == "" {
				continue
			}
			platformID := CanonicalPlatformID(CanonicalPlatformInput{
				Kind:        platformKind,
				Name:        environment,
				Environment: environment,
			})
			if platformID == "" {
				continue
			}
			rpKey := instanceID + "|" + platformID
			if _, ok := seenRuntimePlatforms[rpKey]; ok {
				continue
			}
			seenRuntimePlatforms[rpKey] = struct{}{}
			result.RuntimePlatformRows = append(result.RuntimePlatformRows, RuntimePlatformRow{
				Environment:  environment,
				InstanceID:   instanceID,
				PlatformID:   platformID,
				PlatformKind: platformKind,
				PlatformName: environment,
				RepoID:       candidate.RepoID,
			})
		}
	}

	return result
}

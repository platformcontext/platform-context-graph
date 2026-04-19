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
	Classification   string
	Confidence       float64
	Provenance       []string
}

// ProjectionStats tracks counts produced during projection row building.
type ProjectionStats struct {
	Workloads         int
	Instances         int
	DeploymentSources int
}

// WorkloadRow is one canonical workload upsert payload.
type WorkloadRow struct {
	RepoID         string
	WorkloadID     string
	WorkloadKind   string
	WorkloadName   string
	Classification string
	Confidence     float64
	Provenance     []string
}

// InstanceRow is one canonical workload instance upsert payload.
type InstanceRow struct {
	Environment    string
	InstanceID     string
	RepoID         string
	WorkloadID     string
	WorkloadKind   string
	WorkloadName   string
	Classification string
	Confidence     float64
	Provenance     []string
}

// DeploymentSourceRow is one canonical deployment source edge payload.
type DeploymentSourceRow struct {
	DeploymentRepoID string
	Environment      string
	InstanceID       string
	WorkloadName     string
	Confidence       float64
	Provenance       []string
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
	Stats                ProjectionStats
	WorkloadRows         []WorkloadRow
	InstanceRows         []InstanceRow
	DeploymentSourceRows []DeploymentSourceRow
	RuntimePlatformRows  []RuntimePlatformRow
	RepoDescriptors      []RepoDescriptor
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

// InferWorkloadClassification groups candidates into broad materialization
// classes. Only service and job classifications are allowed to become
// canonical workloads in Wave 1B to avoid weak controller signals creating
// false-positive graph truth.
func InferWorkloadClassification(candidate WorkloadCandidate) string {
	if hasProvenance(candidate.Provenance, "cloudformation_template") {
		return "infrastructure"
	}
	if hasAnyResourceKind(candidate.ResourceKinds, "job", "cronjob") {
		return "job"
	}
	if hasProvenance(candidate.Provenance,
		"k8s_resource",
		"argocd_application",
		"argocd_application_source",
		"argocd_applicationset_deploy_source",
		"dockerfile_runtime",
		"docker_compose_runtime",
	) || hasAnyResourceKind(candidate.ResourceKinds,
		"deployment",
		"service",
		"statefulset",
		"daemonset",
	) {
		return "service"
	}
	if hasProvenance(candidate.Provenance, "jenkins_pipeline", "github_actions_workflow") {
		return "utility"
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
		classification := candidate.Classification
		if classification == "" {
			classification = InferWorkloadClassification(candidate)
		}
		if !isMaterializableWorkloadClassification(classification) {
			continue
		}

		workloadID := fmt.Sprintf("workload:%s", candidate.RepoName)
		workloadKind := InferWorkloadKind(candidate.RepoName, candidate.ResourceKinds)
		confidence := normalizedCandidateConfidence(candidate.Confidence)
		provenance := append([]string(nil), candidate.Provenance...)

		result.RepoDescriptors = append(result.RepoDescriptors, RepoDescriptor{
			RepoID:     candidate.RepoID,
			RepoName:   candidate.RepoName,
			WorkloadID: workloadID,
		})

		if _, ok := seenWorkloads[workloadID]; !ok {
			seenWorkloads[workloadID] = struct{}{}
			result.WorkloadRows = append(result.WorkloadRows, WorkloadRow{
				RepoID:         candidate.RepoID,
				WorkloadID:     workloadID,
				WorkloadKind:   workloadKind,
				WorkloadName:   candidate.RepoName,
				Classification: classification,
				Confidence:     confidence,
				Provenance:     provenance,
			})
			result.Stats.Workloads++
		}

		// Resolve environments: deployment overlay environments first (by
		// deployment repo when linked, otherwise source repo), then namespace
		// fallback.
		var environments []string
		if candidate.DeploymentRepoID != "" {
			environments = deploymentEnvironments[candidate.DeploymentRepoID]
		} else {
			environments = deploymentEnvironments[candidate.RepoID]
		}
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
					Environment:    environment,
					InstanceID:     instanceID,
					RepoID:         candidate.RepoID,
					WorkloadID:     workloadID,
					WorkloadKind:   workloadKind,
					WorkloadName:   candidate.RepoName,
					Classification: classification,
					Confidence:     confidence,
					Provenance:     provenance,
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
						Confidence:       confidence,
						Provenance:       provenance,
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

func isMaterializableWorkloadClassification(classification string) bool {
	switch strings.TrimSpace(strings.ToLower(classification)) {
	case "service", "job":
		return true
	default:
		return false
	}
}

func normalizedCandidateConfidence(confidence float64) float64 {
	if confidence > 0 {
		return confidence
	}
	return 0.90
}

func hasAnyResourceKind(resourceKinds []string, wanted ...string) bool {
	for _, kind := range resourceKinds {
		normalized := strings.ToLower(strings.TrimSpace(kind))
		for _, candidate := range wanted {
			if normalized == candidate {
				return true
			}
		}
	}
	return false
}

func hasProvenance(provenance []string, wanted ...string) bool {
	for _, value := range provenance {
		normalized := strings.ToLower(strings.TrimSpace(value))
		for _, candidate := range wanted {
			if normalized == candidate {
				return true
			}
		}
	}
	return false
}

package reducer

import (
	"fmt"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

// repoSignals aggregates K8s and ArgoCD signal data during candidate
// extraction from fact envelopes.
type repoSignals struct {
	resourceKinds map[string]struct{}
	namespaces    map[string]struct{}
	hasArgoCD     bool
}

// ExtractWorkloadCandidates builds workload candidates and deployment overlay
// environments from fact envelopes for one scope generation. It examines
// repository facts for repo identity and file facts for K8s resources and
// ArgoCD applications to determine which repositories define deployable
// workloads.
//
// Returns (candidates, deploymentEnvironmentsByRepoID).
func ExtractWorkloadCandidates(envelopes []facts.Envelope) ([]WorkloadCandidate, map[string][]string) {
	if len(envelopes) == 0 {
		return nil, nil
	}

	// Pass 1: collect repo identity from the repository fact.
	repos := make(map[string]string) // repo_id → repo_name
	for _, env := range envelopes {
		if env.FactKind != "repository" {
			continue
		}
		repoID := payloadStr(env.Payload, "graph_id")
		repoName := payloadStr(env.Payload, "name")
		if repoID != "" && repoName != "" {
			repos[repoID] = repoName
		}
	}

	// Pass 2: scan file facts for K8s resources and ArgoCD apps.
	signals := make(map[string]*repoSignals)
	deploymentEnvs := make(map[string]map[string]struct{})

	for _, env := range envelopes {
		if env.FactKind != "file" {
			continue
		}
		repoID := payloadStr(env.Payload, "repo_id")
		if repoID == "" {
			continue
		}

		fileData, ok := env.Payload["parsed_file_data"].(map[string]any)
		if !ok {
			continue
		}
		relativePath := payloadStr(env.Payload, "relative_path")

		sig := signals[repoID]
		if sig == nil {
			sig = &repoSignals{
				resourceKinds: make(map[string]struct{}),
				namespaces:    make(map[string]struct{}),
			}
			signals[repoID] = sig
		}

		extractK8sSignals(fileData, sig)
		extractArgoCDSignals(fileData, sig)
		extractOverlayEnvs(repoID, relativePath, deploymentEnvs)
	}

	// Pass 3: build candidates for repos that have workload signals.
	var candidates []WorkloadCandidate
	for repoID, repoName := range repos {
		sig := signals[repoID]
		if sig == nil {
			continue
		}
		if len(sig.resourceKinds) == 0 && !sig.hasArgoCD {
			continue
		}

		candidates = append(candidates, WorkloadCandidate{
			RepoID:        repoID,
			RepoName:      repoName,
			ResourceKinds: sortedKeys(sig.resourceKinds),
			Namespaces:    sortedKeys(sig.namespaces),
		})
	}

	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].RepoName < candidates[j].RepoName
	})

	envResult := make(map[string][]string, len(deploymentEnvs))
	for repoID, envSet := range deploymentEnvs {
		envResult[repoID] = sortedKeys(envSet)
	}

	return candidates, envResult
}

func extractK8sSignals(fileData map[string]any, sig *repoSignals) {
	resources, ok := fileData["k8s_resources"].([]any)
	if !ok {
		return
	}
	for _, item := range resources {
		resource, ok := item.(map[string]any)
		if !ok {
			continue
		}
		kind := strings.ToLower(strings.TrimSpace(fmt.Sprint(resource["kind"])))
		if kind != "" && kind != "<nil>" {
			sig.resourceKinds[kind] = struct{}{}
		}
		ns := strings.TrimSpace(fmt.Sprint(resource["namespace"]))
		if ns != "" && ns != "<nil>" {
			sig.namespaces[ns] = struct{}{}
		}
	}
}

func extractArgoCDSignals(fileData map[string]any, sig *repoSignals) {
	for _, bucket := range []string{"argocd_applications", "argocd_applicationsets"} {
		apps, ok := fileData[bucket].([]any)
		if !ok {
			continue
		}
		if len(apps) > 0 {
			sig.hasArgoCD = true
		}
	}
}

func extractOverlayEnvs(repoID, relativePath string, deploymentEnvs map[string]map[string]struct{}) {
	if relativePath == "" {
		return
	}
	environments := ExtractOverlayEnvironments([]string{relativePath})
	if len(environments) == 0 {
		return
	}
	envSet := deploymentEnvs[repoID]
	if envSet == nil {
		envSet = make(map[string]struct{})
		deploymentEnvs[repoID] = envSet
	}
	for _, env := range environments {
		envSet[env] = struct{}{}
	}
}

func payloadStr(payload map[string]any, key string) string {
	val, ok := payload[key]
	if !ok {
		return ""
	}
	s := strings.TrimSpace(fmt.Sprint(val))
	if s == "<nil>" {
		return ""
	}
	return s
}

func sortedKeys(m map[string]struct{}) []string {
	if len(m) == 0 {
		return nil
	}
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

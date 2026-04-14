package relationships

import (
	"io"
	"strings"

	"gopkg.in/yaml.v3"
)

func discoverKustomizeDocumentEvidence(
	sourceRepoID, filePath string,
	document map[string]any,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact

	appendValues := func(values []string, kind EvidenceKind, confidence float64, rationale string) {
		for _, value := range values {
			evidence = append(evidence, matchCatalog(
				sourceRepoID, value, filePath,
				kind, RelDeploysFrom, confidence, rationale,
				"kustomize", catalog, seen, nil,
			)...)
		}
	}

	appendValues(kustomizeResourceStrings(document), EvidenceKindKustomizeResource, 0.90,
		"Kustomize resources source deployment config from the target repository")
	appendValues(kustomizeHelmStrings(document), EvidenceKindKustomizeHelmChart, 0.89,
		"Kustomize Helm configuration deploys from the target repository")
	appendValues(kustomizeImageStrings(document), EvidenceKindKustomizeImage, 0.86,
		"Kustomize image configuration deploys artifacts from the target repository")

	return evidence
}

func discoverArgoCDDocumentEvidence(
	controlRepoID, filePath string,
	document map[string]any,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact

	for _, repoURL := range argocdApplicationRepoURLs(document) {
		evidence = append(evidence, matchCatalog(
			controlRepoID, repoURL, filePath,
			EvidenceKindArgoCDAppSource, RelDeploysFrom, 0.95,
			"ArgoCD Application source references the target repository",
			"argocd", catalog, seen, nil,
		)...)
	}

	discoveryTargets := argocdApplicationSetDiscoveryTargets(document)
	templateSources := argocdApplicationSetTemplateSources(document)
	if len(discoveryTargets) == 0 || len(templateSources) == 0 {
		return evidence
	}

	for _, discovery := range discoveryTargets {
		for _, configRepo := range matchingCatalogEntries(discovery.repoURL, catalog) {
			if configRepo.RepoID == controlRepoID {
				continue
			}
			evidence = append(evidence, appendDiscoveryEvidence(
				controlRepoID, configRepo, filePath, discovery.path, seen,
			)...)
			for _, templateSource := range templateSources {
				for _, deployedRepo := range matchingCatalogEntries(templateSource, catalog) {
					if deployedRepo.RepoID == configRepo.RepoID || deployedRepo.RepoID == controlRepoID {
						continue
					}
					evidence = append(evidence, appendDeploySourceEvidence(
						controlRepoID, deployedRepo, configRepo, filePath, discovery.path, templateSource, seen,
					)...)
				}
			}
		}
	}

	return evidence
}

type argocdDiscoveryTarget struct {
	repoURL string
	path    string
}

func appendDiscoveryEvidence(
	controlRepoID string,
	configRepo CatalogEntry,
	filePath, discoveryPath string,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	key := evidenceKey{
		EvidenceKind: EvidenceKindArgoCDApplicationSetDiscovery,
		SourceRepoID: controlRepoID,
		TargetRepoID: configRepo.RepoID,
		Path:         filePath,
	}
	if _, ok := seen[key]; ok {
		return nil
	}
	seen[key] = struct{}{}

	return []EvidenceFact{{
		EvidenceKind:     EvidenceKindArgoCDApplicationSetDiscovery,
		RelationshipType: RelDiscoversConfigIn,
		SourceRepoID:     controlRepoID,
		TargetRepoID:     configRepo.RepoID,
		Confidence:       0.99,
		Rationale:        "ArgoCD ApplicationSet discovers config in the target repository",
		Details: map[string]any{
			"path":           filePath,
			"discovery_path": discoveryPath,
			"matched_alias":  firstAlias(configRepo),
			"extractor":      "argocd",
		},
	}}
}

func appendDeploySourceEvidence(
	controlRepoID string,
	deployedRepo, configRepo CatalogEntry,
	filePath, discoveryPath, templateSource string,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	key := evidenceKey{
		EvidenceKind: EvidenceKindArgoCDApplicationSetDeploySource,
		SourceRepoID: deployedRepo.RepoID,
		TargetRepoID: configRepo.RepoID,
		Path:         filePath,
	}
	if _, ok := seen[key]; ok {
		return nil
	}
	seen[key] = struct{}{}

	return []EvidenceFact{{
		EvidenceKind:     EvidenceKindArgoCDApplicationSetDeploySource,
		RelationshipType: RelDeploysFrom,
		SourceRepoID:     deployedRepo.RepoID,
		TargetRepoID:     configRepo.RepoID,
		Confidence:       0.99,
		Rationale:        "The deployed repository sources manifests or overlays from the config repository",
		Details: map[string]any{
			"path":                  filePath,
			"control_plane_repo_id": controlRepoID,
			"config_repo_id":        configRepo.RepoID,
			"discovery_path":        discoveryPath,
			"deploy_repo_url":       templateSource,
			"extractor":             "argocd",
			"matched_alias":         firstAlias(deployedRepo),
		},
	}}
}

func parseYAMLDocuments(content string) []map[string]any {
	decoder := yaml.NewDecoder(strings.NewReader(content))
	var documents []map[string]any
	for {
		var document map[string]any
		err := decoder.Decode(&document)
		if err == nil {
			if len(document) > 0 {
				documents = append(documents, document)
			}
			continue
		}
		if err == io.EOF {
			return documents
		}
		return documents
	}
}

func argocdApplicationRepoURLs(document map[string]any) []string {
	spec, _ := nestedMap(document, "spec")
	if spec == nil {
		return nil
	}
	var result []string
	if source, _ := nestedMap(spec, "source"); source != nil {
		if repoURL := stringValue(source["repoURL"]); repoURL != "" {
			result = append(result, repoURL)
		}
	}
	for _, item := range sliceValue(spec["sources"]) {
		source, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if repoURL := stringValue(source["repoURL"]); repoURL != "" {
			result = append(result, repoURL)
		}
	}
	return uniqueStrings(result)
}

func argocdApplicationSetDiscoveryTargets(document map[string]any) []argocdDiscoveryTarget {
	if !strings.EqualFold(stringValue(document["kind"]), "ApplicationSet") {
		return nil
	}
	spec, _ := nestedMap(document, "spec")
	if spec == nil {
		return nil
	}
	var targets []argocdDiscoveryTarget
	for _, generator := range collectGitGenerators(sliceValue(spec["generators"])) {
		repoURL := stringValue(generator["repoURL"])
		if repoURL == "" {
			continue
		}
		for _, fileEntry := range sliceValue(generator["files"]) {
			entry, ok := fileEntry.(map[string]any)
			if !ok {
				continue
			}
			path := stringValue(entry["path"])
			if path == "" || !strings.Contains(strings.ToLower(path), "config.yaml") {
				continue
			}
			targets = append(targets, argocdDiscoveryTarget{repoURL: repoURL, path: path})
		}
	}
	return targets
}

func argocdApplicationSetTemplateSources(document map[string]any) []string {
	if !strings.EqualFold(stringValue(document["kind"]), "ApplicationSet") {
		return nil
	}
	spec, _ := nestedMap(document, "spec")
	template, _ := nestedMap(spec, "template")
	templateSpec, _ := nestedMap(template, "spec")
	if templateSpec == nil {
		return nil
	}
	return argocdApplicationRepoURLs(map[string]any{"spec": templateSpec})
}

func collectGitGenerators(items []any) []map[string]any {
	var result []map[string]any
	for _, item := range items {
		node, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if gitGen, _ := nestedMap(node, "git"); gitGen != nil {
			result = append(result, gitGen)
		}
		for _, key := range []string{"matrix", "merge"} {
			if nested, _ := nestedMap(node, key); nested != nil {
				result = append(result, collectGitGenerators(sliceValue(nested["generators"]))...)
			}
		}
	}
	return result
}

func kustomizeResourceStrings(document map[string]any) []string {
	return gatherStrings(document, "resources", "components")
}

func kustomizeHelmStrings(document map[string]any) []string {
	return gatherObjectStrings(document, "helmCharts", "name", "repo", "releaseName")
}

func kustomizeImageStrings(document map[string]any) []string {
	return gatherObjectStrings(document, "images", "name", "newName")
}

func gatherStrings(document map[string]any, keys ...string) []string {
	var result []string
	for _, key := range keys {
		for _, item := range sliceValue(document[key]) {
			if value := stringValue(item); value != "" {
				result = append(result, value)
			}
		}
	}
	return uniqueStrings(result)
}

func gatherObjectStrings(document map[string]any, listKey string, fieldKeys ...string) []string {
	var result []string
	for _, item := range sliceValue(document[listKey]) {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}
		for _, key := range fieldKeys {
			if value := stringValue(entry[key]); value != "" {
				result = append(result, value)
			}
		}
	}
	return uniqueStrings(result)
}

func matchingCatalogEntries(candidate string, catalog []CatalogEntry) []CatalogEntry {
	var result []CatalogEntry
	for _, entry := range catalog {
		if matchesEntry(candidate, entry) != "" {
			result = append(result, entry)
		}
	}
	return result
}

func firstAlias(entry CatalogEntry) string {
	if len(entry.Aliases) == 0 {
		return ""
	}
	return entry.Aliases[0]
}

func nestedMap(root map[string]any, key string) (map[string]any, bool) {
	if root == nil {
		return nil, false
	}
	value, ok := root[key]
	if !ok {
		return nil, false
	}
	result, ok := value.(map[string]any)
	return result, ok
}

func sliceValue(value any) []any {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	return items
}

func stringValue(value any) string {
	text, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(text)
}

func uniqueStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	seen := make(map[string]struct{}, len(values))
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
	return result
}

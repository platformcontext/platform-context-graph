package relationships

import (
	"regexp"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

// CatalogEntry maps one repository to its known aliases for matching.
type CatalogEntry struct {
	RepoID  string
	Aliases []string
}

// DiscoverEvidence scans fact envelopes for IaC relationship evidence
// (Terraform, Helm, ArgoCD, Kustomize) and returns discovered evidence facts.
func DiscoverEvidence(envelopes []facts.Envelope, catalog []CatalogEntry) []EvidenceFact {
	if len(envelopes) == 0 || len(catalog) == 0 {
		return nil
	}

	var evidence []EvidenceFact
	seen := make(map[evidenceKey]struct{})

	for i := range envelopes {
		discovered := discoverFromEnvelope(envelopes[i], catalog, seen)
		evidence = append(evidence, discovered...)
	}

	return evidence
}

// evidenceKey deduplicates evidence within a single discovery pass.
type evidenceKey struct {
	EvidenceKind   EvidenceKind
	SourceRepoID   string
	TargetRepoID   string
	SourceEntityID string
	TargetEntityID string
	Path           string
}

// terraformPattern describes one regex-based Terraform evidence extractor.
type terraformPattern struct {
	EvidenceKind     EvidenceKind
	RelationshipType RelationshipType
	Pattern          *regexp.Regexp
	Confidence       float64
	Rationale        string
}

var terraformPatterns = []terraformPattern{
	{
		EvidenceKind:     EvidenceKindTerraformAppRepo,
		RelationshipType: RelProvisionsDependencyFor,
		Pattern:          regexp.MustCompile(`(?i)\bapp_repo\b\s*=\s*"([^"]+)"`),
		Confidence:       0.99,
		Rationale:        "Terraform app_repo points at the target repository",
	},
	{
		EvidenceKind:     EvidenceKindTerraformAppName,
		RelationshipType: RelProvisionsDependencyFor,
		Pattern:          regexp.MustCompile(`(?i)\bapp_name\b\s*=\s*"([^"]+)"`),
		Confidence:       0.94,
		Rationale:        "Terraform app_name matches the target repository name",
	},
	{
		EvidenceKind:     EvidenceKindTerraformGitHubRepo,
		RelationshipType: RelProvisionsDependencyFor,
		Pattern:          regexp.MustCompile(`(?i)github\.com[:/][^/"'\s]+/([A-Za-z0-9._-]+)(?:\.git)?`),
		Confidence:       0.98,
		Rationale:        "Terraform GitHub reference points at the target repository",
	},
	{
		EvidenceKind:     EvidenceKindTerraformGitHubActions,
		RelationshipType: RelProvisionsDependencyFor,
		Pattern:          regexp.MustCompile(`(?i)repo:[^/:\s]+/([A-Za-z0-9._-]+):`),
		Confidence:       0.97,
		Rationale:        "Terraform GitHub Actions subject references the target repository",
	},
	{
		EvidenceKind:     EvidenceKindTerraformConfigPath,
		RelationshipType: RelProvisionsDependencyFor,
		Pattern:          regexp.MustCompile(`(?i)/(?:configd|api)/([A-Za-z0-9._-]+)/`),
		Confidence:       0.90,
		Rationale:        "Terraform configuration path references the target repository name",
	},
}

// helmChartFilenames are the recognized Helm chart metadata files.
var helmChartFilenames = map[string]struct{}{
	"chart.yaml": {},
	"chart.yml":  {},
}

// kustomizationFilenames are the recognized Kustomize files.
var kustomizationFilenames = map[string]struct{}{
	"kustomization.yaml": {},
	"kustomization.yml":  {},
}

// discoverFromEnvelope extracts evidence from a single fact envelope based
// on its artifact type and content.
func discoverFromEnvelope(
	envelope facts.Envelope,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	artifactType, _ := envelope.Payload["artifact_type"].(string)
	filePath, _ := envelope.Payload["relative_path"].(string)
	content, _ := envelope.Payload["content"].(string)
	sourceRepoID := envelope.ScopeID

	// Fall back to Go collector content fact payload keys. The collector
	// emits content_path and content_body instead of relative_path and
	// content. Both formats are supported so evidence discovery works
	// regardless of how facts were produced.
	if filePath == "" {
		filePath, _ = envelope.Payload["content_path"].(string)
	}
	if content == "" {
		content, _ = envelope.Payload["content_body"].(string)
	}

	if content == "" || filePath == "" {
		return nil
	}

	var evidence []EvidenceFact

	switch {
	case isTerraformArtifact(artifactType, filePath):
		evidence = append(evidence, discoverTerraformEvidence(
			sourceRepoID, filePath, content, catalog, seen,
		)...)
	case isHelmArtifact(artifactType, filePath):
		evidence = append(evidence, discoverHelmEvidence(
			sourceRepoID, filePath, content, catalog, seen,
		)...)
	case isKustomizeArtifact(filePath):
		evidence = append(evidence, discoverKustomizeEvidence(
			sourceRepoID, filePath, content, catalog, seen,
		)...)
	case isArgoCDArtifact(artifactType, content):
		evidence = append(evidence, discoverArgoCDEvidence(
			sourceRepoID, filePath, content, catalog, seen,
		)...)
	}

	return evidence
}

// discoverTerraformEvidence applies Terraform regex patterns against file content.
func discoverTerraformEvidence(
	sourceRepoID, filePath, content string,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact

	for _, tp := range terraformPatterns {
		matches := tp.Pattern.FindAllStringSubmatch(content, -1)
		for _, match := range matches {
			if len(match) < 2 {
				continue
			}
			candidate := strings.TrimSpace(match[1])
			evidence = append(evidence, matchCatalog(
				sourceRepoID, candidate, filePath,
				tp.EvidenceKind, tp.RelationshipType, tp.Confidence, tp.Rationale,
				"terraform", catalog, seen, nil,
			)...)
		}
	}

	evidence = append(evidence, discoverTerraformSchemaEvidence(
		sourceRepoID, filePath, content, catalog, seen,
	)...)

	return evidence
}

// discoverHelmEvidence extracts DEPLOYS_FROM evidence from Helm chart content.
func discoverHelmEvidence(
	sourceRepoID, filePath, content string,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	lowerName := strings.ToLower(fileBaseName(filePath))
	var evidenceKind EvidenceKind
	var confidence float64
	var rationale string

	if _, ok := helmChartFilenames[lowerName]; ok {
		evidenceKind = EvidenceKindHelmChart
		confidence = 0.90
		rationale = "Helm chart metadata references the target repository"
	} else {
		evidenceKind = EvidenceKindHelmValues
		confidence = 0.84
		rationale = "Helm values reference the target repository"
	}

	var evidence []EvidenceFact
	for _, candidate := range extractYAMLStringValues(content) {
		evidence = append(evidence, matchCatalog(
			sourceRepoID, candidate, filePath,
			evidenceKind, RelDeploysFrom, confidence, rationale,
			"helm", catalog, seen, nil,
		)...)
	}

	return evidence
}

// discoverKustomizeEvidence extracts DEPLOYS_FROM evidence from Kustomize overlays.
func discoverKustomizeEvidence(
	sourceRepoID, filePath, content string,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact
	for _, document := range parseYAMLDocuments(content) {
		evidence = append(evidence, discoverKustomizeDocumentEvidence(
			sourceRepoID, filePath, document, catalog, seen,
		)...)
	}
	for _, candidate := range extractYAMLStringValues(content) {
		evidence = append(evidence, matchCatalog(
			sourceRepoID, candidate, filePath,
			EvidenceKindKustomizeResource, RelDeploysFrom, 0.90,
			"Kustomize resources source deployment config from the target repository",
			"kustomize", catalog, seen, nil,
		)...)
	}

	return evidence
}

// discoverArgoCDEvidence extracts ArgoCD Application source references.
func discoverArgoCDEvidence(
	sourceRepoID, filePath, content string,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact
	for _, document := range parseYAMLDocuments(content) {
		evidence = append(evidence, discoverArgoCDDocumentEvidence(
			sourceRepoID, filePath, document, catalog, seen,
		)...)
	}

	return evidence
}

// matchCatalog matches a candidate string against catalog entries and returns
// evidence facts for each match.
func matchCatalog(
	sourceRepoID, candidate, filePath string,
	evidenceKind EvidenceKind,
	relType RelationshipType,
	confidence float64,
	rationale, extractor string,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
	extraDetails map[string]any,
) []EvidenceFact {
	var evidence []EvidenceFact

	for _, entry := range catalog {
		if entry.RepoID == sourceRepoID {
			continue
		}
		matchedAlias := matchesEntry(candidate, entry)
		if matchedAlias == "" {
			continue
		}
		key := evidenceKey{
			EvidenceKind:   evidenceKind,
			SourceRepoID:   sourceRepoID,
			TargetRepoID:   entry.RepoID,
			SourceEntityID: "",
			TargetEntityID: "",
			Path:           filePath,
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		details := map[string]any{
			"path":          filePath,
			"matched_alias": matchedAlias,
			"matched_value": candidate,
			"extractor":     extractor,
		}
		for key, value := range extraDetails {
			details[key] = value
		}
		evidence = append(evidence, EvidenceFact{
			EvidenceKind:     evidenceKind,
			RelationshipType: relType,
			SourceRepoID:     sourceRepoID,
			TargetRepoID:     entry.RepoID,
			Confidence:       confidence,
			Rationale:        rationale,
			Details:          details,
		})
	}

	return evidence
}

// matchesEntry checks if a candidate string matches any alias of a catalog entry.
// Returns the matched alias or empty string.
func matchesEntry(candidate string, entry CatalogEntry) string {
	lowerCandidate := strings.ToLower(candidate)
	for _, alias := range entry.Aliases {
		if strings.Contains(lowerCandidate, strings.ToLower(alias)) {
			return alias
		}
	}
	return ""
}

// extractYAMLStringValues extracts potential string values from YAML content
// using simple pattern matching (not a full YAML parser).
var yamlStringPattern = regexp.MustCompile(`:\s*['"]?([A-Za-z0-9._/-]+)['"]?`)

func extractYAMLStringValues(content string) []string {
	matches := yamlStringPattern.FindAllStringSubmatch(content, -1)
	values := make([]string, 0, len(matches))
	seen := make(map[string]struct{})
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		val := strings.TrimSpace(match[1])
		if val == "" {
			continue
		}
		if _, ok := seen[val]; ok {
			continue
		}
		seen[val] = struct{}{}
		values = append(values, val)
	}
	return values
}

// isTerraformArtifact checks if a file is a Terraform/Terragrunt file.
func isTerraformArtifact(artifactType, filePath string) bool {
	if artifactType == "terraform" || artifactType == "terragrunt" {
		return true
	}
	lower := strings.ToLower(filePath)
	return strings.HasSuffix(lower, ".tf") ||
		strings.HasSuffix(lower, ".tf.json") ||
		strings.HasSuffix(lower, ".hcl")
}

// isHelmArtifact checks if a file is a Helm chart file.
func isHelmArtifact(artifactType, filePath string) bool {
	if artifactType == "helm" {
		return true
	}
	lowerName := strings.ToLower(fileBaseName(filePath))
	if _, ok := helmChartFilenames[lowerName]; ok {
		return true
	}
	return strings.HasPrefix(lowerName, "values") &&
		(strings.HasSuffix(lowerName, ".yaml") || strings.HasSuffix(lowerName, ".yml"))
}

// isKustomizeArtifact checks if a file is a Kustomize file.
func isKustomizeArtifact(filePath string) bool {
	lowerName := strings.ToLower(fileBaseName(filePath))
	_, ok := kustomizationFilenames[lowerName]
	return ok
}

// isArgoCDArtifact checks if content appears to be an ArgoCD Application spec.
func isArgoCDArtifact(artifactType, content string) bool {
	if artifactType == "argocd" {
		return true
	}
	return strings.Contains(content, "kind: Application") ||
		strings.Contains(content, "kind: ApplicationSet")
}

// fileBaseName returns the last path component of a file path.
func fileBaseName(path string) string {
	idx := strings.LastIndex(path, "/")
	if idx < 0 {
		return path
	}
	return path[idx+1:]
}

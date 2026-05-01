package query

import (
	"context"
	"fmt"
	"net/http"
	"path"
	"regexp"
	"sort"
	"strings"
)

const (
	iacDeadCapability = "iac_quality.dead_iac"
	iacDeadFileLimit  = 10000
)

// IaCHandler serves infrastructure-as-code quality query routes.
type IaCHandler struct {
	Content ContentStore
	Profile QueryProfile
}

// Mount registers IaC quality routes on the given mux.
func (h *IaCHandler) Mount(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v0/iac/dead", h.handleDeadIaC)
}

func (h *IaCHandler) profile() QueryProfile {
	if h == nil {
		return ProfileProduction
	}
	return NormalizeQueryProfile(string(h.Profile))
}

type deadIaCRequest struct {
	RepoID           string   `json:"repo_id"`
	RepoIDs          []string `json:"repo_ids"`
	Families         []string `json:"families"`
	IncludeAmbiguous bool     `json:"include_ambiguous"`
	Limit            int      `json:"limit"`
}

type deadIaCFinding struct {
	ID           string   `json:"id"`
	Family       string   `json:"family"`
	RepoID       string   `json:"repo_id"`
	Artifact     string   `json:"artifact"`
	Reachability string   `json:"reachability"`
	Finding      string   `json:"finding"`
	Confidence   float64  `json:"confidence"`
	Evidence     []string `json:"evidence"`
	Limitations  []string `json:"limitations,omitempty"`
}

type iacArtifact struct {
	family   string
	repoID   string
	path     string
	name     string
	evidence []string
}

type iacReferenceIndex struct {
	used      map[string][]string
	ambiguous map[string][]string
}

func (h *IaCHandler) handleDeadIaC(w http.ResponseWriter, r *http.Request) {
	if capabilityUnsupported(h.profile(), iacDeadCapability) {
		WriteContractError(
			w,
			r,
			http.StatusNotImplemented,
			"dead-IaC analysis requires an explicit indexed IaC scope",
			ErrorCodeUnsupportedCapability,
			iacDeadCapability,
			h.profile(),
			requiredProfile(iacDeadCapability),
		)
		return
	}

	var req deadIaCRequest
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	repoIDs := normalizeDeadIaCRepoScope(req)
	if len(repoIDs) == 0 {
		WriteError(w, http.StatusBadRequest, "repo_id or repo_ids is required")
		return
	}
	if h == nil || h.Content == nil {
		WriteError(w, http.StatusServiceUnavailable, "content store is required")
		return
	}
	if req.Limit <= 0 {
		req.Limit = 100
	}
	if req.Limit > 500 {
		req.Limit = 500
	}

	filesByRepo, err := loadIaCDeadFiles(r.Context(), h.Content, repoIDs)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	findings := analyzeDeadIaC(filesByRepo, familyFilter(req.Families), req.IncludeAmbiguous)
	if len(findings) > req.Limit {
		findings = findings[:req.Limit]
	}

	WriteSuccess(w, r, http.StatusOK, map[string]any{
		"repo_ids":        repoIDs,
		"findings":        findings,
		"findings_count":  len(findings),
		"truth_basis":     "content_scope",
		"analysis_status": "derived_candidate_analysis",
		"limitations": []string{
			"bounded to the requested repository scope",
			"dynamic templates and variable-selected references are reported as ambiguous",
			"exact dead-IaC requires reducer-materialized usage rows",
		},
	}, BuildTruthEnvelope(h.profile(), iacDeadCapability, TruthBasisContentIndex, "derived from bounded IaC content references"))
}

func normalizeDeadIaCRepoScope(req deadIaCRequest) []string {
	seen := map[string]struct{}{}
	var repoIDs []string
	add := func(repoID string) {
		repoID = strings.TrimSpace(repoID)
		if repoID == "" {
			return
		}
		if _, ok := seen[repoID]; ok {
			return
		}
		seen[repoID] = struct{}{}
		repoIDs = append(repoIDs, repoID)
	}
	add(req.RepoID)
	for _, repoID := range req.RepoIDs {
		add(repoID)
	}
	sort.Strings(repoIDs)
	return repoIDs
}

func loadIaCDeadFiles(ctx context.Context, content ContentStore, repoIDs []string) (map[string][]FileContent, error) {
	filesByRepo := make(map[string][]FileContent, len(repoIDs))
	for _, repoID := range repoIDs {
		files, err := content.ListRepoFiles(ctx, repoID, iacDeadFileLimit)
		if err != nil {
			return nil, fmt.Errorf("list IaC files for %q: %w", repoID, err)
		}
		for i, file := range files {
			if strings.TrimSpace(file.Content) != "" || !isDeadIaCRelevantFile(file.RelativePath) {
				continue
			}
			loaded, err := content.GetFileContent(ctx, repoID, file.RelativePath)
			if err != nil {
				return nil, fmt.Errorf("get IaC file %q from %q: %w", file.RelativePath, repoID, err)
			}
			if loaded != nil {
				files[i] = *loaded
			}
		}
		filesByRepo[repoID] = files
	}
	return filesByRepo, nil
}

func analyzeDeadIaC(filesByRepo map[string][]FileContent, families map[string]bool, includeAmbiguous bool) []deadIaCFinding {
	artifacts := discoverIaCArtifacts(filesByRepo, families)
	refs := buildIaCReferenceIndex(filesByRepo)
	findings := make([]deadIaCFinding, 0)
	for _, artifact := range artifacts {
		key := artifactKey(artifact.family, artifact.name)
		if evidence := refs.used[key]; len(evidence) > 0 {
			continue
		}
		if evidence := refs.ambiguous[key]; len(evidence) > 0 {
			if !includeAmbiguous {
				continue
			}
			findings = append(findings, newDeadIaCFinding(artifact, "ambiguous", "ambiguous_dynamic_reference", 0.40, evidence))
			continue
		}
		findings = append(findings, newDeadIaCFinding(artifact, "unused", "candidate_dead_iac", 0.75, artifact.evidence))
	}
	sort.Slice(findings, func(i, j int) bool {
		return findings[i].ID < findings[j].ID
	})
	return findings
}

func discoverIaCArtifacts(filesByRepo map[string][]FileContent, families map[string]bool) []iacArtifact {
	seen := map[string]struct{}{}
	var artifacts []iacArtifact
	for repoID, files := range filesByRepo {
		for _, file := range files {
			if modulePath, name, ok := terraformModuleArtifact(file.RelativePath); ok && familyEnabled(families, "terraform") {
				artifacts = appendUniqueArtifact(artifacts, seen, iacArtifact{
					family: "terraform", repoID: repoID, path: modulePath, name: name,
					evidence: []string{file.RelativePath + ": module directory exists"},
				})
			}
			if chartPath, name, ok := helmChartArtifact(file.RelativePath); ok && familyEnabled(families, "helm") {
				artifacts = appendUniqueArtifact(artifacts, seen, iacArtifact{
					family: "helm", repoID: repoID, path: chartPath, name: name,
					evidence: []string{file.RelativePath + ": chart metadata exists"},
				})
			}
			if rolePath, name, ok := ansibleRoleArtifact(file.RelativePath); ok && familyEnabled(families, "ansible") {
				artifacts = appendUniqueArtifact(artifacts, seen, iacArtifact{
					family: "ansible", repoID: repoID, path: rolePath, name: name,
					evidence: []string{file.RelativePath + ": role task entrypoint exists"},
				})
			}
		}
	}
	return artifacts
}

func appendUniqueArtifact(artifacts []iacArtifact, seen map[string]struct{}, artifact iacArtifact) []iacArtifact {
	key := artifact.family + ":" + artifact.repoID + ":" + artifact.path
	if _, ok := seen[key]; ok {
		return artifacts
	}
	seen[key] = struct{}{}
	return append(artifacts, artifact)
}

func buildIaCReferenceIndex(filesByRepo map[string][]FileContent) iacReferenceIndex {
	index := iacReferenceIndex{used: map[string][]string{}, ambiguous: map[string][]string{}}
	reachedPlaybooks := collectReachedAnsiblePlaybooks(filesByRepo)
	for _, files := range filesByRepo {
		for _, file := range files {
			content := file.Content
			if content == "" {
				continue
			}
			recordTerraformReferences(index, file, content)
			recordHelmReferences(index, file, content)
			recordAnsibleReferences(index, file, content, reachedPlaybooks)
		}
	}
	return index
}

func newDeadIaCFinding(artifact iacArtifact, reachability, finding string, confidence float64, evidence []string) deadIaCFinding {
	limitations := []string(nil)
	if reachability == "ambiguous" {
		limitations = []string{"dynamic reference requires renderer or runtime evidence before cleanup"}
	}
	return deadIaCFinding{
		ID:           artifact.family + ":" + artifact.repoID + ":" + artifact.path,
		Family:       artifact.family,
		RepoID:       artifact.repoID,
		Artifact:     artifact.path,
		Reachability: reachability,
		Finding:      finding,
		Confidence:   confidence,
		Evidence:     append([]string(nil), evidence...),
		Limitations:  limitations,
	}
}

func familyFilter(families []string) map[string]bool {
	if len(families) == 0 {
		return nil
	}
	filter := map[string]bool{}
	for _, family := range families {
		family = strings.ToLower(strings.TrimSpace(family))
		if family != "" {
			filter[family] = true
		}
	}
	return filter
}

func familyEnabled(filter map[string]bool, family string) bool {
	return len(filter) == 0 || filter[family]
}

func artifactKey(family, name string) string {
	return family + ":" + strings.ToLower(strings.TrimSpace(name))
}

func addReference(index map[string][]string, family, name string, evidence ...string) {
	name = strings.Trim(strings.TrimSpace(name), `"'`)
	if name == "" {
		return
	}
	key := artifactKey(family, path.Base(name))
	index[key] = append(index[key], evidence...)
}

func isDeadIaCRelevantFile(relativePath string) bool {
	lower := strings.ToLower(relativePath)
	return strings.HasSuffix(lower, ".tf") ||
		strings.HasSuffix(lower, ".hcl") ||
		strings.HasSuffix(lower, ".yaml") ||
		strings.HasSuffix(lower, ".yml") ||
		strings.Contains(lower, "jenkinsfile")
}

func terraformModuleArtifact(relativePath string) (string, string, bool) {
	parts := strings.Split(path.Clean(relativePath), "/")
	for i := 0; i < len(parts)-1; i++ {
		if parts[i] == "modules" && parts[i+1] != "" {
			return strings.Join(parts[:i+2], "/"), parts[i+1], true
		}
	}
	return "", "", false
}

func helmChartArtifact(relativePath string) (string, string, bool) {
	clean := path.Clean(relativePath)
	parts := strings.Split(clean, "/")
	for i := 0; i < len(parts)-2; i++ {
		if parts[i] == "charts" && parts[i+1] != "" && parts[i+2] == "Chart.yaml" {
			return strings.Join(parts[:i+2], "/"), parts[i+1], true
		}
	}
	return "", "", false
}

func ansibleRoleArtifact(relativePath string) (string, string, bool) {
	clean := path.Clean(relativePath)
	parts := strings.Split(clean, "/")
	for i := 0; i < len(parts)-3; i++ {
		if parts[i] == "roles" && parts[i+1] != "" && parts[i+2] == "tasks" {
			return strings.Join(parts[:i+2], "/"), parts[i+1], true
		}
	}
	return "", "", false
}

var (
	terraformSourcePattern = regexp.MustCompile(`(?m)\bsource\s*=\s*["']([^"']+)["']`)
	ansiblePlaybookPattern = regexp.MustCompile(`ansible-playbook\s+([^\s'"]+)`)
)

func recordTerraformReferences(index iacReferenceIndex, file FileContent, content string) {
	for _, match := range terraformSourcePattern.FindAllStringSubmatch(content, -1) {
		source := match[1]
		evidence := file.RelativePath + ": terraform source " + source
		if strings.Contains(source, "${") || strings.Contains(source, "{{") {
			for _, token := range referenceTokens(content) {
				addReference(index.ambiguous, "terraform", token, evidence)
			}
			continue
		}
		if strings.Contains(source, "/modules/") {
			addReference(index.used, "terraform", source, evidence)
		}
	}
}

func recordHelmReferences(index iacReferenceIndex, file FileContent, content string) {
	for _, token := range strings.Fields(content) {
		cleaned := strings.Trim(token, `"'`)
		if !strings.Contains(cleaned, "charts/") {
			continue
		}
		evidence := file.RelativePath + ": helm chart reference " + cleaned
		if strings.Contains(cleaned, "{{") || strings.Contains(cleaned, "${") {
			for _, quoted := range referenceTokens(content) {
				addReference(index.ambiguous, "helm", quoted, evidence)
			}
			continue
		}
		_, after, _ := strings.Cut(cleaned, "charts/")
		addReference(index.used, "helm", after, evidence)
	}
}

func collectReachedAnsiblePlaybooks(filesByRepo map[string][]FileContent) map[string][]string {
	reached := map[string][]string{}
	for _, files := range filesByRepo {
		for _, file := range files {
			for _, match := range ansiblePlaybookPattern.FindAllStringSubmatch(file.Content, -1) {
				playbook := normalizeAnsiblePlaybookPath(match[1])
				reached[playbook] = append(reached[playbook], file.RelativePath+": ansible-playbook "+match[1])
			}
		}
	}
	return reached
}

func recordAnsibleReferences(index iacReferenceIndex, file FileContent, content string, reachedPlaybooks map[string][]string) {
	playbook := normalizeAnsiblePlaybookPath(file.RelativePath)
	controllerEvidence := reachedPlaybooks[playbook]
	if len(controllerEvidence) == 0 {
		return
	}
	if strings.Contains(content, "{{") {
		for _, token := range referenceTokens(content) {
			addReference(index.ambiguous, "ansible", token, append(controllerEvidence, file.RelativePath+": dynamic role reference")...)
		}
		return
	}
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "- ") {
			addReference(index.used, "ansible", strings.TrimSpace(strings.TrimPrefix(line, "- ")), append(controllerEvidence, file.RelativePath+": role reference")...)
		}
	}
}

func normalizeAnsiblePlaybookPath(raw string) string {
	clean := path.Clean(strings.Trim(raw, `"'`))
	if idx := strings.Index(clean, "playbooks/"); idx >= 0 {
		return clean[idx:]
	}
	return clean
}

func referenceTokens(content string) []string {
	matches := regexp.MustCompile(`[A-Za-z0-9_.-]+`).FindAllString(content, -1)
	tokens := make([]string, 0, len(matches))
	seen := map[string]struct{}{}
	for _, match := range matches {
		token := strings.TrimSpace(match)
		if token == "" {
			continue
		}
		if _, ok := seen[token]; ok {
			continue
		}
		seen[token] = struct{}{}
		tokens = append(tokens, token)
	}
	return tokens
}

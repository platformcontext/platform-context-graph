package query

import (
	"context"
	"fmt"
	"net/http"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/iacreachability"
)

const (
	iacDeadCapability = "iac_quality.dead_iac"
	iacDeadFileLimit  = 10000
)

// IaCHandler serves infrastructure-as-code quality query routes.
type IaCHandler struct {
	Content      ContentStore
	Reachability IaCReachabilityStore
	Profile      QueryProfile
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

// IaCReachabilityStore reads reducer-materialized IaC cleanup findings.
type IaCReachabilityStore interface {
	ListLatestCleanupFindings(
		ctx context.Context,
		repoIDs []string,
		families []string,
		includeAmbiguous bool,
		limit int,
	) ([]IaCReachabilityFindingRow, error)
	HasLatestRows(ctx context.Context, repoIDs []string, families []string) (bool, error)
}

// IaCReachabilityFindingRow is the query-facing shape of one materialized IaC
// cleanup row.
type IaCReachabilityFindingRow struct {
	ID           string
	Family       string
	RepoID       string
	ArtifactPath string
	Reachability string
	Finding      string
	Confidence   float64
	Evidence     []string
	Limitations  []string
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
	repoIDs, err := h.resolveRepositoryScope(r.Context(), repoIDs)
	if err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	if req.Limit <= 0 {
		req.Limit = 100
	}
	if req.Limit > 500 {
		req.Limit = 500
	}
	families := normalizeDeadIaCFamilies(req.Families)
	if h != nil && h.Reachability != nil {
		rows, err := h.Reachability.ListLatestCleanupFindings(
			r.Context(),
			repoIDs,
			families,
			req.IncludeAmbiguous,
			req.Limit,
		)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if len(rows) > 0 {
			writeMaterializedDeadIaC(w, r, h.profile(), repoIDs, materializedDeadIaCFindings(rows))
			return
		}
		hasRows, err := h.Reachability.HasLatestRows(r.Context(), repoIDs, families)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, err.Error())
			return
		}
		if hasRows {
			writeMaterializedDeadIaC(w, r, h.profile(), repoIDs, nil)
			return
		}
	}
	if h == nil || h.Content == nil {
		WriteError(w, http.StatusServiceUnavailable, "content store is required")
		return
	}

	filesByRepo, err := loadIaCDeadFiles(r.Context(), h.Content, repoIDs)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	findings := analyzeDeadIaC(filesByRepo, iacreachability.FamilyFilter(families), req.IncludeAmbiguous)
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

func writeMaterializedDeadIaC(
	w http.ResponseWriter,
	r *http.Request,
	profile QueryProfile,
	repoIDs []string,
	findings []deadIaCFinding,
) {
	WriteSuccess(w, r, http.StatusOK, map[string]any{
		"repo_ids":        repoIDs,
		"findings":        findings,
		"findings_count":  len(findings),
		"truth_basis":     "materialized_reducer_rows",
		"analysis_status": "materialized_reachability",
		"limitations": []string{
			"dynamic templates and variable-selected references are reported as ambiguous",
		},
	}, BuildTruthEnvelope(profile, iacDeadCapability, TruthBasisSemanticFacts, "resolved from reducer-materialized IaC reachability rows"))
}

func materializedDeadIaCFindings(rows []IaCReachabilityFindingRow) []deadIaCFinding {
	findings := make([]deadIaCFinding, 0, len(rows))
	for _, row := range rows {
		findings = append(findings, deadIaCFinding{
			ID:           row.ID,
			Family:       row.Family,
			RepoID:       row.RepoID,
			Artifact:     row.ArtifactPath,
			Reachability: row.Reachability,
			Finding:      row.Finding,
			Confidence:   row.Confidence,
			Evidence:     append([]string(nil), row.Evidence...),
			Limitations:  append([]string(nil), row.Limitations...),
		})
	}
	return findings
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

func (h *IaCHandler) resolveRepositoryScope(ctx context.Context, selectors []string) ([]string, error) {
	if h == nil || h.Content == nil {
		return selectors, nil
	}
	resolved := make([]string, 0, len(selectors))
	seen := make(map[string]struct{}, len(selectors))
	for _, selector := range selectors {
		repoID, err := resolveRepositorySelectorExact(ctx, nil, h.Content, selector)
		if err != nil {
			return nil, err
		}
		if _, ok := seen[repoID]; ok {
			continue
		}
		seen[repoID] = struct{}{}
		resolved = append(resolved, repoID)
	}
	sort.Strings(resolved)
	return resolved, nil
}

func normalizeDeadIaCFamilies(raw []string) []string {
	seen := map[string]struct{}{}
	var families []string
	for _, family := range raw {
		family = strings.ToLower(strings.TrimSpace(family))
		if family == "" {
			continue
		}
		if _, ok := seen[family]; ok {
			continue
		}
		seen[family] = struct{}{}
		families = append(families, family)
	}
	sort.Strings(families)
	return families
}

func loadIaCDeadFiles(ctx context.Context, content ContentStore, repoIDs []string) (map[string][]iacreachability.File, error) {
	filesByRepo := make(map[string][]iacreachability.File, len(repoIDs))
	for _, repoID := range repoIDs {
		files, err := content.ListRepoFiles(ctx, repoID, iacDeadFileLimit)
		if err != nil {
			return nil, fmt.Errorf("list IaC files for %q: %w", repoID, err)
		}
		for i, file := range files {
			if strings.TrimSpace(file.Content) != "" || !iacreachability.RelevantFile(file.RelativePath) {
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
		filesByRepo[repoID] = queryFilesToIaCFiles(files)
	}
	return filesByRepo, nil
}

func queryFilesToIaCFiles(files []FileContent) []iacreachability.File {
	result := make([]iacreachability.File, 0, len(files))
	for _, file := range files {
		if !iacreachability.RelevantFile(file.RelativePath) {
			continue
		}
		result = append(result, iacreachability.File{
			RepoID:       file.RepoID,
			RelativePath: file.RelativePath,
			Content:      file.Content,
		})
	}
	return result
}

func analyzeDeadIaC(
	filesByRepo map[string][]iacreachability.File,
	families map[string]bool,
	includeAmbiguous bool,
) []deadIaCFinding {
	rows := iacreachability.Analyze(filesByRepo, iacreachability.Options{
		Families:         families,
		IncludeAmbiguous: includeAmbiguous,
	})
	rows = iacreachability.CleanupRows(rows, includeAmbiguous)
	findings := make([]deadIaCFinding, 0, len(rows))
	for _, row := range rows {
		findings = append(findings, deadIaCFinding{
			ID:           row.ID,
			Family:       row.Family,
			RepoID:       row.RepoID,
			Artifact:     row.ArtifactPath,
			Reachability: string(row.Reachability),
			Finding:      string(row.Finding),
			Confidence:   row.Confidence,
			Evidence:     append([]string(nil), row.Evidence...),
			Limitations:  append([]string(nil), row.Limitations...),
		})
	}
	return findings
}

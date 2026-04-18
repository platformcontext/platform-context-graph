package query

import (
	"errors"
	"net/http"
)

// ContentHandler serves HTTP endpoints for reading file and entity content
// from the Postgres content store.
type ContentHandler struct {
	Content *ContentReader
}

// Mount registers content query routes on the given mux.
func (h *ContentHandler) Mount(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v0/content/files/read", h.readFile)
	mux.HandleFunc("POST /api/v0/content/files/lines", h.readFileLines)
	mux.HandleFunc("POST /api/v0/content/entities/read", h.readEntity)
	mux.HandleFunc("POST /api/v0/content/files/search", h.searchFiles)
	mux.HandleFunc("POST /api/v0/content/entities/search", h.searchEntities)
}

// readFile reads full file content.
// POST /api/v0/content/files/read
// Body: {"repo_id": "...", "relative_path": "..."}
func (h *ContentHandler) readFile(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RepoID       string `json:"repo_id"`
		RelativePath string `json:"relative_path"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.RepoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}
	if req.RelativePath == "" {
		WriteError(w, http.StatusBadRequest, "relative_path is required")
		return
	}

	fc, err := h.Content.GetFileContent(r.Context(), req.RepoID, req.RelativePath)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if fc == nil {
		WriteError(w, http.StatusNotFound, "file not found")
		return
	}

	WriteJSON(w, http.StatusOK, fc)
}

// readFileLines reads a line range from a file.
// POST /api/v0/content/files/lines
// Body: {"repo_id": "...", "relative_path": "...", "start_line": 1, "end_line": 50}
func (h *ContentHandler) readFileLines(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RepoID       string `json:"repo_id"`
		RelativePath string `json:"relative_path"`
		StartLine    int    `json:"start_line"`
		EndLine      int    `json:"end_line"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.RepoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}
	if req.RelativePath == "" {
		WriteError(w, http.StatusBadRequest, "relative_path is required")
		return
	}

	fc, err := h.Content.GetFileLines(r.Context(), req.RepoID, req.RelativePath, req.StartLine, req.EndLine)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if fc == nil {
		WriteError(w, http.StatusNotFound, "file not found")
		return
	}

	WriteJSON(w, http.StatusOK, fc)
}

// readEntity reads entity content by entity_id.
// POST /api/v0/content/entities/read
// Body: {"entity_id": "..."}
func (h *ContentHandler) readEntity(w http.ResponseWriter, r *http.Request) {
	var req struct {
		EntityID string `json:"entity_id"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.EntityID == "" {
		WriteError(w, http.StatusBadRequest, "entity_id is required")
		return
	}

	ec, err := h.Content.GetEntityContent(r.Context(), req.EntityID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if ec == nil {
		WriteError(w, http.StatusNotFound, "entity not found")
		return
	}

	WriteJSON(w, http.StatusOK, ec)
}

// searchFiles searches file content by pattern.
// POST /api/v0/content/files/search
// Body: {"repo_id": "...", "query": "...", "limit": 50}
func (h *ContentHandler) searchFiles(w http.ResponseWriter, r *http.Request) {
	req, err := readContentSearchRequest(r)
	if err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := req.validate(); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	results, err := h.Content.SearchFileContent(r.Context(), req.repoID(), req.pattern(), req.limit())
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"results": results,
		"count":   len(results),
	})
}

// searchEntities searches entity source cache by pattern.
// POST /api/v0/content/entities/search
// Body: {"repo_id": "...", "query": "...", "limit": 50}
func (h *ContentHandler) searchEntities(w http.ResponseWriter, r *http.Request) {
	req, err := readContentSearchRequest(r)
	if err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := req.validate(); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	results, err := h.Content.SearchEntityContent(r.Context(), req.repoID(), req.pattern(), req.limit())
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"results": results,
		"count":   len(results),
	})
}

type contentSearchRequest struct {
	RepoID  string   `json:"repo_id"`
	RepoIDs []string `json:"repo_ids"`
	Query   string   `json:"query"`
	Pattern string   `json:"pattern"`
	Limit   int      `json:"limit"`
}

func readContentSearchRequest(r *http.Request) (contentSearchRequest, error) {
	var req contentSearchRequest
	if err := ReadJSON(r, &req); err != nil {
		return contentSearchRequest{}, err
	}
	return req, nil
}

func (req contentSearchRequest) validate() error {
	if len(req.RepoIDs) > 1 {
		return errors.New("repo_ids may contain at most one value")
	}
	if req.repoID() == "" {
		return errors.New("repo_id is required")
	}
	if req.pattern() == "" {
		return errors.New("query is required")
	}
	return nil
}

func (req contentSearchRequest) repoID() string {
	if req.RepoID != "" {
		return req.RepoID
	}
	if len(req.RepoIDs) == 1 {
		return req.RepoIDs[0]
	}
	return ""
}

func (req contentSearchRequest) pattern() string {
	if req.Query != "" {
		return req.Query
	}
	return req.Pattern
}

func (req contentSearchRequest) limit() int {
	if req.Limit > 0 {
		return req.Limit
	}
	return 50
}

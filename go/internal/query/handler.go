package query

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
)

// WriteJSON writes a JSON response with the given status code.
func WriteJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
}

// WriteError writes a JSON error response.
func WriteError(w http.ResponseWriter, status int, message string) {
	WriteJSON(w, status, map[string]any{
		"error":  http.StatusText(status),
		"detail": message,
	})
}

// ReadJSON decodes a JSON request body into v.
func ReadJSON(r *http.Request, v any) error {
	if r.Body == nil {
		return fmt.Errorf("request body is required")
	}
	defer func() { _ = r.Body.Close() }()
	dec := json.NewDecoder(r.Body)
	if err := dec.Decode(v); err != nil {
		return fmt.Errorf("invalid JSON: %w", err)
	}
	return nil
}

// QueryParam returns a trimmed query parameter value.
func QueryParam(r *http.Request, key string) string {
	return strings.TrimSpace(r.URL.Query().Get(key))
}

// QueryParamInt returns a query parameter as int with a default.
func QueryParamInt(r *http.Request, key string, defaultVal int) int {
	raw := QueryParam(r, key)
	if raw == "" {
		return defaultVal
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return defaultVal
	}
	return n
}

// PathParam extracts a path segment by position from a ServeMux pattern.
// For routes like "/api/v0/repositories/{repo_id}/context", use PathParam(r, "repo_id").
func PathParam(r *http.Request, name string) string {
	return strings.TrimSpace(r.PathValue(name))
}

// APIRouter builds the top-level /api/v0 mux for all query endpoints.
type APIRouter struct {
	Repositories *RepositoryHandler
	Entities     *EntityHandler
	Code         *CodeHandler
	Content      *ContentHandler
	Infra        *InfraHandler
	Impact       *ImpactHandler
	Status       *StatusHandler
	Compare      *CompareHandler
}

// Mount registers all query-layer HTTP routes on the given mux.
func (a *APIRouter) Mount(mux *http.ServeMux) {
	// Health
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		WriteJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// OpenAPI spec
	mux.HandleFunc("GET /api/v0/openapi.json", ServeOpenAPI)

	// Repositories
	if a.Repositories != nil {
		a.Repositories.Mount(mux)
	}

	// Entities
	if a.Entities != nil {
		a.Entities.Mount(mux)
	}

	// Code
	if a.Code != nil {
		a.Code.Mount(mux)
	}

	// Content
	if a.Content != nil {
		a.Content.Mount(mux)
	}

	// Infra
	if a.Infra != nil {
		a.Infra.Mount(mux)
	}

	// Impact
	if a.Impact != nil {
		a.Impact.Mount(mux)
	}

	// Status
	if a.Status != nil {
		a.Status.Mount(mux)
	}

	// Compare
	if a.Compare != nil {
		a.Compare.Mount(mux)
	}
}

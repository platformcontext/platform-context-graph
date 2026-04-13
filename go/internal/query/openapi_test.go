package query

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestServeOpenAPI(t *testing.T) {
	req := httptest.NewRequest("GET", "/api/v0/openapi.json", nil)
	w := httptest.NewRecorder()

	ServeOpenAPI(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	contentType := w.Header().Get("Content-Type")
	if contentType != "application/json; charset=utf-8" {
		t.Errorf("expected Content-Type application/json; charset=utf-8, got %s", contentType)
	}

	// Verify it's valid JSON
	var spec map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &spec); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	// Verify required OpenAPI fields
	if spec["openapi"] != "3.0.3" {
		t.Errorf("expected openapi version 3.0.3, got %v", spec["openapi"])
	}

	info, ok := spec["info"].(map[string]interface{})
	if !ok {
		t.Fatal("info field missing or invalid")
	}

	if info["title"] != "Platform Context Graph API" {
		t.Errorf("unexpected title: %v", info["title"])
	}

	paths, ok := spec["paths"].(map[string]interface{})
	if !ok {
		t.Fatal("paths field missing or invalid")
	}

	// Verify some key endpoints exist
	expectedPaths := []string{
		"/health",
		"/api/v0/repositories",
		"/api/v0/entities/resolve",
		"/api/v0/code/search",
		"/api/v0/content/files/read",
		"/api/v0/infra/resources/search",
		"/api/v0/impact/blast-radius",
		"/api/v0/status/pipeline",
		"/api/v0/compare/environments",
		"/api/v0/openapi.json",
	}

	for _, path := range expectedPaths {
		if _, exists := paths[path]; !exists {
			t.Errorf("expected path %s not found in spec", path)
		}
	}

	// Verify components section exists
	components, ok := spec["components"].(map[string]interface{})
	if !ok {
		t.Fatal("components field missing or invalid")
	}

	schemas, ok := components["schemas"].(map[string]interface{})
	if !ok {
		t.Fatal("components.schemas missing or invalid")
	}

	// Verify some key schemas
	expectedSchemas := []string{"Repository", "EntityRef", "ErrorResponse", "Relationship"}
	for _, schema := range expectedSchemas {
		if _, exists := schemas[schema]; !exists {
			t.Errorf("expected schema %s not found", schema)
		}
	}
}

func TestAPIRouter_OpenAPIEndpoint(t *testing.T) {
	router := &APIRouter{}
	mux := http.NewServeMux()
	router.Mount(mux)

	req := httptest.NewRequest("GET", "/api/v0/openapi.json", nil)
	w := httptest.NewRecorder()

	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected status 200, got %d", w.Code)
	}

	var spec map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &spec); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	if spec["openapi"] != "3.0.3" {
		t.Errorf("expected openapi version 3.0.3, got %v", spec["openapi"])
	}
}

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
		"/api/v0/code/language-query",
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

func TestOpenAPISpec_ContentEntitySchemasExposeMetadata(t *testing.T) {
	var spec map[string]any
	if err := json.Unmarshal([]byte(OpenAPISpec), &spec); err != nil {
		t.Fatalf("json.Unmarshal(OpenAPISpec) error = %v, want nil", err)
	}

	paths := mustMapField(t, spec, "paths")
	readPath := mustMapField(t, paths, "/api/v0/content/entities/read")
	readPost := mustMapField(t, readPath, "post")
	readResponses := mustMapField(t, readPost, "responses")
	readOK := mustMapField(t, readResponses, "200")
	readContent := mustMapField(t, mustMapField(t, readOK, "content"), "application/json")
	readSchema := mustMapField(t, readContent, "schema")
	if got, want := readSchema["$ref"], "#/components/schemas/EntityContent"; got != want {
		t.Fatalf("content/entities/read schema ref = %#v, want %#v", got, want)
	}

	searchPath := mustMapField(t, paths, "/api/v0/content/entities/search")
	searchPost := mustMapField(t, searchPath, "post")
	searchResponses := mustMapField(t, searchPost, "responses")
	searchOK := mustMapField(t, searchResponses, "200")
	searchContent := mustMapField(t, mustMapField(t, searchOK, "content"), "application/json")
	searchSchema := mustMapField(t, searchContent, "schema")
	if got, want := searchSchema["$ref"], "#/components/schemas/EntityContentSearchResponse"; got != want {
		t.Fatalf("content/entities/search schema ref = %#v, want %#v", got, want)
	}

	components := mustMapField(t, spec, "components")
	schemas := mustMapField(t, components, "schemas")
	entitySchema := mustMapField(t, schemas, "EntityContent")
	entityProperties := mustMapField(t, entitySchema, "properties")
	metadata := mustMapField(t, entityProperties, "metadata")
	if got, want := metadata["type"], "object"; got != want {
		t.Fatalf("EntityContent.metadata.type = %#v, want %#v", got, want)
	}

	entityRefSchema := mustMapField(t, schemas, "EntityRef")
	entityRefProperties := mustMapField(t, entityRefSchema, "properties")
	entityRefMetadata := mustMapField(t, entityRefProperties, "metadata")
	if got, want := entityRefMetadata["type"], "object"; got != want {
		t.Fatalf("EntityRef.metadata.type = %#v, want %#v", got, want)
	}

	entityContextPath := mustMapField(t, paths, "/api/v0/entities/{entity_id}/context")
	entityContextGet := mustMapField(t, entityContextPath, "get")
	entityContextResponses := mustMapField(t, entityContextGet, "responses")
	entityContextOK := mustMapField(t, entityContextResponses, "200")
	entityContextContent := mustMapField(t, mustMapField(t, entityContextOK, "content"), "application/json")
	entityContextSchema := mustMapField(t, entityContextContent, "schema")
	entityContextProperties := mustMapField(t, entityContextSchema, "properties")
	entityContextMetadata := mustMapField(t, entityContextProperties, "metadata")
	if got, want := entityContextMetadata["type"], "object"; got != want {
		t.Fatalf("entity context metadata.type = %#v, want %#v", got, want)
	}

	codeSearchPath := mustMapField(t, paths, "/api/v0/code/search")
	codeSearchPost := mustMapField(t, codeSearchPath, "post")
	codeSearchResponses := mustMapField(t, codeSearchPost, "responses")
	codeSearchOK := mustMapField(t, codeSearchResponses, "200")
	codeSearchContent := mustMapField(t, mustMapField(t, codeSearchOK, "content"), "application/json")
	codeSearchSchema := mustMapField(t, codeSearchContent, "schema")
	if got, want := codeSearchSchema["$ref"], "#/components/schemas/CodeSearchResponse"; got != want {
		t.Fatalf("code/search schema ref = %#v, want %#v", got, want)
	}

	languageQueryPath := mustMapField(t, paths, "/api/v0/code/language-query")
	languageQueryPost := mustMapField(t, languageQueryPath, "post")
	languageQueryBody := mustMapField(t, mustMapField(t, languageQueryPost, "requestBody"), "content")
	languageQueryJSON := mustMapField(t, languageQueryBody, "application/json")
	languageQuerySchema := mustMapField(t, mustMapField(t, languageQueryJSON, "schema"), "properties")
	entityType := mustMapField(t, languageQuerySchema, "entity_type")
	enumValues, ok := entityType["enum"].([]any)
	if !ok {
		t.Fatalf("language-query entity_type enum type = %T, want []any", entityType["enum"])
	}
	if !containsValue(enumValues, "type_alias") ||
		!containsValue(enumValues, "type_annotation") ||
		!containsValue(enumValues, "component") ||
		!containsValue(enumValues, "terragrunt_dependency") ||
		!containsValue(enumValues, "terragrunt_local") ||
		!containsValue(enumValues, "terragrunt_input") {
		t.Fatalf("language-query entity_type enum = %#v, want content-backed entity types", enumValues)
	}
}

func mustMapField(t *testing.T, parent map[string]any, key string) map[string]any {
	t.Helper()

	value, ok := parent[key]
	if !ok {
		t.Fatalf("missing key %q", key)
	}
	typed, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("key %q type = %T, want map[string]any", key, value)
	}
	return typed
}

func containsValue(values []any, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}

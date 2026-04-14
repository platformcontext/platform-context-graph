package query

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSupportedLanguages(t *testing.T) {
	langs := SupportedLanguages()
	if len(langs) != 15 {
		t.Errorf("expected 15 supported languages, got %d: %v", len(langs), langs)
	}
	// Verify sorted order.
	for i := 1; i < len(langs); i++ {
		if langs[i] < langs[i-1] {
			t.Errorf("languages not sorted: %q comes after %q", langs[i], langs[i-1])
		}
	}
	// Spot-check a few.
	expected := map[string]bool{"go": true, "python": true, "rust": true, "typescript": true}
	langSet := make(map[string]bool, len(langs))
	for _, l := range langs {
		langSet[l] = true
	}
	for e := range expected {
		if !langSet[e] {
			t.Errorf("expected language %q not found", e)
		}
	}
}

func TestSupportedEntityTypes(t *testing.T) {
	types := SupportedEntityTypes()
	if len(types) != 11 {
		t.Errorf("expected 11 supported entity types, got %d: %v", len(types), types)
	}
	expected := map[string]bool{
		"repository": true, "directory": true, "file": true,
		"function": true, "class": true, "struct": true,
	}
	typeSet := make(map[string]bool, len(types))
	for _, typ := range types {
		typeSet[typ] = true
	}
	for e := range expected {
		if !typeSet[e] {
			t.Errorf("expected entity type %q not found", e)
		}
	}
}

func TestBuildExtensionFilter(t *testing.T) {
	tests := []struct {
		name string
		exts []string
		want string
	}{
		{"empty", nil, ""},
		{"single", []string{".go"}, " OR f.name ENDS WITH '.go'"},
		{"multiple", []string{".py", ".pyi"}, " OR f.name ENDS WITH '.py' OR f.name ENDS WITH '.pyi'"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := buildExtensionFilter(tt.exts)
			if got != tt.want {
				t.Errorf("buildExtensionFilter(%v) = %q, want %q", tt.exts, got, tt.want)
			}
		})
	}
}

func TestBuildLanguageCypher_Function(t *testing.T) {
	cypher, params := buildLanguageCypher("python", "Function", "my_func", "repo:123", 10)

	if cypher == "" {
		t.Fatal("expected non-empty cypher")
	}
	// Must contain the Function label.
	if !searchString(cypher, "Function") {
		t.Error("cypher should contain Function label")
	}
	// Must have language param.
	if params["language"] != "python" {
		t.Errorf("language param = %v, want python", params["language"])
	}
	if params["repo_id"] != "repo:123" {
		t.Errorf("repo_id param = %v, want repo:123", params["repo_id"])
	}
	if params["query"] != "my_func" {
		t.Errorf("query param = %v, want my_func", params["query"])
	}
	if params["limit"] != 10 {
		t.Errorf("limit param = %v, want 10", params["limit"])
	}
	// Must filter by language.
	if !searchString(cypher, "$language") {
		t.Error("cypher should reference $language parameter")
	}
	// Must filter by repo.
	if !searchString(cypher, "$repo_id") {
		t.Error("cypher should reference $repo_id parameter")
	}
	// Must filter by name.
	if !searchString(cypher, "$query") {
		t.Error("cypher should reference $query parameter")
	}
}

func TestBuildLanguageCypher_Repository(t *testing.T) {
	cypher, params := buildLanguageCypher("go", "Repository", "", "", 25)

	if !searchString(cypher, "Repository") {
		t.Error("cypher should contain Repository label")
	}
	if params["limit"] != 25 {
		t.Errorf("limit param = %v, want 25", params["limit"])
	}
	// No repo_id or query filters when empty.
	if _, ok := params["repo_id"]; ok {
		t.Error("repo_id should not be set when empty")
	}
	if _, ok := params["query"]; ok {
		t.Error("query should not be set when empty")
	}
}

func TestBuildLanguageCypher_File(t *testing.T) {
	cypher, params := buildLanguageCypher("rust", "File", "main", "", 10)

	if !searchString(cypher, "File") {
		t.Error("cypher should contain File label")
	}
	// Rust extension filter.
	if !searchString(cypher, ".rs") {
		t.Error("cypher should contain .rs extension filter")
	}
	if params["query"] != "main" {
		t.Errorf("query param = %v, want main", params["query"])
	}
}

func TestBuildLanguageCypher_Directory(t *testing.T) {
	cypher, _ := buildLanguageCypher("java", "Directory", "", "repo:x", 5)

	if !searchString(cypher, "Directory") {
		t.Error("cypher should contain Directory label")
	}
	if !searchString(cypher, ".java") {
		t.Error("cypher should contain .java extension filter")
	}
}

func TestBuildLanguageResult_Entity(t *testing.T) {
	row := map[string]any{
		"entity_id":  "func:abc",
		"name":       "doStuff",
		"labels":     []any{"Function"},
		"file_path":  "src/main.go",
		"repo_id":    "repo:123",
		"repo_name":  "my-repo",
		"language":   "go",
		"start_line": int64(10),
		"end_line":   int64(20),
	}

	result := buildLanguageResult(row, "Function")
	if result["entity_id"] != "func:abc" {
		t.Errorf("entity_id = %v", result["entity_id"])
	}
	if result["name"] != "doStuff" {
		t.Errorf("name = %v", result["name"])
	}
	if result["file_path"] != "src/main.go" {
		t.Errorf("file_path = %v", result["file_path"])
	}
	if result["start_line"] != 10 {
		t.Errorf("start_line = %v", result["start_line"])
	}
}

func TestBuildLanguageResult_Repository(t *testing.T) {
	row := map[string]any{
		"id":         "repo:123",
		"name":       "my-repo",
		"local_path": "/repos/my-repo",
		"remote_url": "https://github.com/org/my-repo",
		"file_count": int64(42),
	}

	result := buildLanguageResult(row, "Repository")
	if result["id"] != "repo:123" {
		t.Errorf("id = %v", result["id"])
	}
	if result["file_count"] != 42 {
		t.Errorf("file_count = %v", result["file_count"])
	}
}

func TestHandleLanguageQuery_MissingLanguage(t *testing.T) {
	h := &LanguageQueryHandler{}
	mux := http.NewServeMux()
	h.Mount(mux)

	body := `{"entity_type":"function"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v0/code/language-query", bytes.NewBufferString(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestHandleLanguageQuery_MissingEntityType(t *testing.T) {
	h := &LanguageQueryHandler{}
	mux := http.NewServeMux()
	h.Mount(mux)

	body := `{"language":"python"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v0/code/language-query", bytes.NewBufferString(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestHandleLanguageQuery_UnsupportedLanguage(t *testing.T) {
	h := &LanguageQueryHandler{}
	mux := http.NewServeMux()
	h.Mount(mux)

	body := `{"language":"fortran","entity_type":"function"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v0/code/language-query", bytes.NewBufferString(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	detail, _ := resp["detail"].(string)
	if !searchString(detail, "fortran") {
		t.Errorf("error should mention fortran, got: %s", detail)
	}
}

func TestHandleLanguageQuery_UnsupportedEntityType(t *testing.T) {
	h := &LanguageQueryHandler{}
	mux := http.NewServeMux()
	h.Mount(mux)

	body := `{"language":"python","entity_type":"interface"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v0/code/language-query", bytes.NewBufferString(body))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	detail, _ := resp["detail"].(string)
	if !searchString(detail, "interface") {
		t.Errorf("error should mention interface, got: %s", detail)
	}
}

func TestHandleLanguageQuery_InvalidJSON(t *testing.T) {
	h := &LanguageQueryHandler{}
	mux := http.NewServeMux()
	h.Mount(mux)

	req := httptest.NewRequest(http.MethodPost, "/api/v0/code/language-query", bytes.NewBufferString("{bad"))
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestJoinKeys(t *testing.T) {
	m := map[string]bool{"c": true, "a": true, "b": true}
	got := joinKeys(m)
	if got != "a, b, c" {
		t.Errorf("joinKeys = %q, want %q", got, "a, b, c")
	}
}

func TestSortStrings(t *testing.T) {
	s := []string{"go", "c", "rust", "java", "dart"}
	sortStrings(s)
	for i := 1; i < len(s); i++ {
		if s[i] < s[i-1] {
			t.Errorf("not sorted at index %d: %v", i, s)
		}
	}
}

func TestLanguageFileExtensions_Coverage(t *testing.T) {
	// Every supported language should have extension mappings.
	for lang := range supportedLanguages {
		exts, ok := languageFileExtensions[lang]
		if !ok || len(exts) == 0 {
			t.Errorf("language %q has no file extension mappings", lang)
		}
	}
}

func TestBuildLanguageCypher_AllEntityTypes(t *testing.T) {
	// Verify all entity types produce valid cypher.
	for typeName, label := range supportedEntityTypes {
		cypher, params := buildLanguageCypher("python", label, "", "", 10)
		if cypher == "" {
			t.Errorf("entity type %q produced empty cypher", typeName)
		}
		if params["language"] != "python" {
			t.Errorf("entity type %q: language param = %v", typeName, params["language"])
		}
	}
}

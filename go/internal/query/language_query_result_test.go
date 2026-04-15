package query

import "testing"

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

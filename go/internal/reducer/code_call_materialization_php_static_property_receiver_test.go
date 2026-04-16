package reducer

import (
	"path/filepath"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestExtractCodeCallRowsResolvesPHPStaticPropertyReceiverChainsUsingTypedPropertyInference(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	callerPath := filepath.Join(repoRoot, "registry.php")
	servicePath := filepath.Join(repoRoot, "service.php")

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-php",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":       "repo-php",
				"relative_path": "registry.php",
				"parsed_file_data": map[string]any{
					"path": callerPath,
					"functions": []any{
						map[string]any{
							"name":          "boot",
							"class_context": "Registry",
							"line_number":   3,
							"end_line":      5,
							"uid":           "content-entity:php-registry-boot",
						},
					},
					"function_calls": []any{
						map[string]any{
							"name":              "info",
							"full_name":         "self::$service.info",
							"inferred_obj_type": "Service",
							"line_number":       4,
							"lang":              "php",
						},
					},
				},
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":       "repo-php",
				"relative_path": "service.php",
				"parsed_file_data": map[string]any{
					"path": servicePath,
					"functions": []any{
						map[string]any{
							"name":          "info",
							"class_context": "Service",
							"line_number":   1,
							"end_line":      2,
							"uid":           "content-entity:php-service-info",
						},
					},
				},
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1", len(rows))
	}
	if got, want := rows[0]["callee_entity_id"], "content-entity:php-service-info"; got != want {
		t.Fatalf("callee_entity_id = %#v, want %#v", got, want)
	}
}

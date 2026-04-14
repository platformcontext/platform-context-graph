package reducer

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestExtractCodeCallRowsBuildsCanonicalEntityPairs(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactKind: "repository",
			Payload: map[string]any{
				"repo_id": "repo-payments",
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":       "repo-payments",
				"relative_path": "caller.py",
				"parsed_file_data": map[string]any{
					"path": "caller.py",
					"functions": []any{
						map[string]any{
							"name":        "handle",
							"line_number": 3,
							"uid":         "content-entity:caller",
						},
					},
					"function_calls_scip": []any{
						map[string]any{
							"caller_file":   "caller.py",
							"caller_line":   3,
							"caller_symbol": "pkg/caller#handle().",
							"callee_file":   "callee.py",
							"callee_line":   1,
							"callee_symbol": "pkg/callee#callee().",
						},
					},
				},
			},
		},
		{
			FactKind: "file",
			Payload: map[string]any{
				"repo_id":       "repo-payments",
				"relative_path": "callee.py",
				"parsed_file_data": map[string]any{
					"path": "callee.py",
					"functions": []any{
						map[string]any{
							"name":        "callee",
							"line_number": 1,
							"uid":         "content-entity:callee",
						},
					},
				},
			},
		},
	}

	repoIDs, rows := ExtractCodeCallRows(envelopes)
	if len(repoIDs) != 1 || repoIDs[0] != "repo-payments" {
		t.Fatalf("repoIDs = %v, want [repo-payments]", repoIDs)
	}
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1", len(rows))
	}
	if got, want := rows[0]["caller_entity_id"], "content-entity:caller"; got != want {
		t.Fatalf("caller_entity_id = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["callee_entity_id"], "content-entity:callee"; got != want {
		t.Fatalf("callee_entity_id = %#v, want %#v", got, want)
	}
}

func TestCodeCallMaterializationHandlerWritesCanonicalCalls(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC)
	handler := CodeCallMaterializationHandler{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{
					FactKind: "repository",
					Payload: map[string]any{
						"repo_id": "repo-payments",
					},
				},
				{
					FactKind: "file",
					Payload: map[string]any{
						"repo_id":       "repo-payments",
						"relative_path": "caller.py",
						"parsed_file_data": map[string]any{
							"path": "caller.py",
							"functions": []any{
								map[string]any{
									"name":        "handle",
									"line_number": 3,
									"uid":         "content-entity:caller",
								},
							},
							"function_calls_scip": []any{
								map[string]any{
									"caller_file":   "caller.py",
									"caller_line":   3,
									"caller_symbol": "pkg/caller#handle().",
									"callee_file":   "callee.py",
									"callee_line":   1,
									"callee_symbol": "pkg/callee#callee().",
								},
							},
						},
					},
				},
				{
					FactKind: "file",
					Payload: map[string]any{
						"repo_id":       "repo-payments",
						"relative_path": "callee.py",
						"parsed_file_data": map[string]any{
							"path": "callee.py",
							"functions": []any{
								map[string]any{
									"name":        "callee",
									"line_number": 1,
									"uid":         "content-entity:callee",
								},
							},
						},
					},
				},
			},
		},
		EdgeWriter: &recordingCodeCallEdgeWriter{},
	}

	intent := Intent{
		IntentID:        "intent-code-calls-1",
		ScopeID:         "scope-payments",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainCodeCallMaterialization,
		Cause:           "parser call graph follow-up required",
		EntityKeys:      []string{"repo-payments"},
		RelatedScopeIDs: []string{"scope-payments"},
		EnqueuedAt:      now,
		AvailableAt:     now,
		Status:          IntentStatusPending,
	}

	result, err := handler.Handle(context.Background(), intent)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if result.Status != ResultStatusSucceeded {
		t.Fatalf("result.Status = %q, want %q", result.Status, ResultStatusSucceeded)
	}
	if result.CanonicalWrites != 1 {
		t.Fatalf("result.CanonicalWrites = %d, want 1", result.CanonicalWrites)
	}

	writer := handler.EdgeWriter.(*recordingCodeCallEdgeWriter)
	if writer.retractDomain != DomainCodeCalls {
		t.Fatalf("retractDomain = %q, want %q", writer.retractDomain, DomainCodeCalls)
	}
	if writer.writeDomain != DomainCodeCalls {
		t.Fatalf("writeDomain = %q, want %q", writer.writeDomain, DomainCodeCalls)
	}
	if len(writer.writeRows) != 1 {
		t.Fatalf("len(writeRows) = %d, want 1", len(writer.writeRows))
	}
	if got, want := writer.writeRows[0].Payload["caller_entity_id"], "content-entity:caller"; got != want {
		t.Fatalf("caller_entity_id = %#v, want %#v", got, want)
	}
	if got, want := writer.writeRows[0].Payload["callee_entity_id"], "content-entity:callee"; got != want {
		t.Fatalf("callee_entity_id = %#v, want %#v", got, want)
	}
}

type recordingCodeCallEdgeWriter struct {
	retractDomain string
	retractRows   []SharedProjectionIntentRow
	writeDomain   string
	writeRows     []SharedProjectionIntentRow
}

func (r *recordingCodeCallEdgeWriter) RetractEdges(
	_ context.Context,
	domain string,
	rows []SharedProjectionIntentRow,
	_ string,
) error {
	r.retractDomain = domain
	r.retractRows = append(r.retractRows, rows...)
	return nil
}

func (r *recordingCodeCallEdgeWriter) WriteEdges(
	_ context.Context,
	domain string,
	rows []SharedProjectionIntentRow,
	_ string,
) error {
	r.writeDomain = domain
	r.writeRows = append(r.writeRows, rows...)
	return nil
}

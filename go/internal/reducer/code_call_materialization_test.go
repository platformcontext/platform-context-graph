package reducer

import (
	"context"
	"fmt"
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

func TestExtractCodeCallRowsBuildsCanonicalEntityPairsFromGenericCalls(t *testing.T) {
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
				"relative_path": "service.py",
				"parsed_file_data": map[string]any{
					"path": "service.py",
					"functions": []any{
						map[string]any{
							"name":        "handle",
							"line_number": 3,
							"end_line":    6,
							"uid":         "content-entity:handle",
						},
						map[string]any{
							"name":        "helper",
							"line_number": 8,
							"end_line":    10,
							"uid":         "content-entity:helper",
						},
					},
					"function_calls": []any{
						map[string]any{
							"name":        "helper",
							"line_number": 4,
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
	if got, want := rows[0]["caller_entity_id"], "content-entity:handle"; got != want {
		t.Fatalf("caller_entity_id = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["callee_entity_id"], "content-entity:helper"; got != want {
		t.Fatalf("callee_entity_id = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["caller_file"], "service.py"; got != want {
		t.Fatalf("caller_file = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["callee_file"], "service.py"; got != want {
		t.Fatalf("callee_file = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["ref_line"], 4; got != want {
		t.Fatalf("ref_line = %#v, want %#v", got, want)
	}
}

func TestExtractCodeCallRowsSkipsAmbiguousGenericCalls(t *testing.T) {
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
				"relative_path": "service.py",
				"parsed_file_data": map[string]any{
					"path": "service.py",
					"functions": []any{
						map[string]any{
							"name":        "handle",
							"line_number": 3,
							"end_line":    6,
							"uid":         "content-entity:handle",
						},
						map[string]any{
							"name":        "helper",
							"line_number": 8,
							"end_line":    10,
							"uid":         "content-entity:helper-a",
						},
						map[string]any{
							"name":        "helper",
							"line_number": 12,
							"end_line":    14,
							"uid":         "content-entity:helper-b",
						},
					},
					"function_calls": []any{
						map[string]any{
							"name":        "helper",
							"line_number": 4,
						},
					},
				},
			},
		},
	}

	_, rows := ExtractCodeCallRows(envelopes)
	if len(rows) != 0 {
		t.Fatalf("len(rows) = %d, want 0 for ambiguous generic call", len(rows))
	}
}

func TestExtractCodeCallRowsDisambiguatesGenericCallsUsingFullName(t *testing.T) {
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
				"relative_path": "service.py",
				"parsed_file_data": map[string]any{
					"path": "service.py",
					"functions": []any{
						map[string]any{
							"name":        "handle",
							"line_number": 3,
							"end_line":    6,
							"uid":         "content-entity:handle",
						},
						map[string]any{
							"name":          "request",
							"class_context": "Service",
							"line_number":   8,
							"end_line":      10,
							"uid":           "content-entity:service-request",
						},
						map[string]any{
							"name":          "request",
							"class_context": "Queue",
							"line_number":   12,
							"end_line":      14,
							"uid":           "content-entity:queue-request",
						},
					},
					"function_calls": []any{
						map[string]any{
							"name":        "request",
							"full_name":   "Service.request",
							"call_kind":   "function_call",
							"line_number": 4,
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
	if got, want := rows[0]["caller_entity_id"], "content-entity:handle"; got != want {
		t.Fatalf("caller_entity_id = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["callee_entity_id"], "content-entity:service-request"; got != want {
		t.Fatalf("callee_entity_id = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["full_name"], "Service.request"; got != want {
		t.Fatalf("full_name = %#v, want %#v", got, want)
	}
	if got, want := rows[0]["call_kind"], "function_call"; got != want {
		t.Fatalf("call_kind = %#v, want %#v", got, want)
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
	if writer.retractEvidenceSource != codeCallEvidenceSource {
		t.Fatalf("retractEvidenceSource = %q, want %q", writer.retractEvidenceSource, codeCallEvidenceSource)
	}
	if writer.writeDomain != DomainCodeCalls {
		t.Fatalf("writeDomain = %q, want %q", writer.writeDomain, DomainCodeCalls)
	}
	if writer.writeEvidenceSource != codeCallEvidenceSource {
		t.Fatalf("writeEvidenceSource = %q, want %q", writer.writeEvidenceSource, codeCallEvidenceSource)
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

// --- CanonicalNodeChecker pre-flight tests ---

type fakeCanonicalNodeChecker struct {
	exists bool
	err    error
}

func (f *fakeCanonicalNodeChecker) HasCanonicalCodeTargets(_ context.Context) (bool, error) {
	return f.exists, f.err
}

func TestCodeCallMaterializationHandlerSkipsWhenNoCanonicalTargets(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC)
	writer := &recordingCodeCallEdgeWriter{}
	handler := CodeCallMaterializationHandler{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{FactKind: "repository", Payload: map[string]any{"repo_id": "repo-1"}},
				{FactKind: "file", Payload: map[string]any{
					"repo_id": "repo-1", "relative_path": "main.py",
					"parsed_file_data": map[string]any{
						"path": "main.py",
						"functions": []any{
							map[string]any{"name": "fn", "line_number": 1, "uid": "uid:fn"},
						},
					},
				}},
			},
		},
		EdgeWriter:           writer,
		CanonicalNodeChecker: &fakeCanonicalNodeChecker{exists: false},
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-1",
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		Domain:       DomainCodeCallMaterialization,
		EnqueuedAt:   now,
		AvailableAt:  now,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if result.Status != ResultStatusSucceeded {
		t.Fatalf("result.Status = %q, want %q", result.Status, ResultStatusSucceeded)
	}
	if result.CanonicalWrites != 0 {
		t.Fatalf("result.CanonicalWrites = %d, want 0 (should skip)", result.CanonicalWrites)
	}
	if len(writer.writeRows) != 0 {
		t.Fatalf("EdgeWriter.WriteEdges called with %d rows, want 0", len(writer.writeRows))
	}
	if len(writer.retractRows) != 0 {
		t.Fatalf("EdgeWriter.RetractEdges called with %d rows, want 0", len(writer.retractRows))
	}
}

func TestCodeCallMaterializationHandlerProceedsWhenCanonicalTargetsExist(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC)
	writer := &recordingCodeCallEdgeWriter{}
	handler := CodeCallMaterializationHandler{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{FactKind: "repository", Payload: map[string]any{"repo_id": "repo-1"}},
				{FactKind: "file", Payload: map[string]any{
					"repo_id": "repo-1", "relative_path": "caller.py",
					"parsed_file_data": map[string]any{
						"path": "caller.py",
						"functions": []any{
							map[string]any{"name": "handle", "line_number": 3, "uid": "uid:caller"},
						},
						"function_calls_scip": []any{
							map[string]any{
								"caller_file": "caller.py", "caller_line": 3,
								"caller_symbol": "pkg/caller#handle().",
								"callee_file": "callee.py", "callee_line": 1,
								"callee_symbol": "pkg/callee#callee().",
							},
						},
					},
				}},
				{FactKind: "file", Payload: map[string]any{
					"repo_id": "repo-1", "relative_path": "callee.py",
					"parsed_file_data": map[string]any{
						"path": "callee.py",
						"functions": []any{
							map[string]any{"name": "callee", "line_number": 1, "uid": "uid:callee"},
						},
					},
				}},
			},
		},
		EdgeWriter:           writer,
		CanonicalNodeChecker: &fakeCanonicalNodeChecker{exists: true},
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-1",
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		Domain:       DomainCodeCallMaterialization,
		EnqueuedAt:   now,
		AvailableAt:  now,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if result.CanonicalWrites == 0 {
		t.Fatal("result.CanonicalWrites = 0, want > 0 when canonical targets exist")
	}
}

func TestCodeCallMaterializationHandlerProceedsWhenCheckerNil(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC)
	writer := &recordingCodeCallEdgeWriter{}
	handler := CodeCallMaterializationHandler{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{FactKind: "repository", Payload: map[string]any{"repo_id": "repo-1"}},
				{FactKind: "file", Payload: map[string]any{
					"repo_id": "repo-1", "relative_path": "caller.py",
					"parsed_file_data": map[string]any{
						"path": "caller.py",
						"functions": []any{
							map[string]any{"name": "handle", "line_number": 3, "uid": "uid:caller"},
						},
						"function_calls_scip": []any{
							map[string]any{
								"caller_file": "caller.py", "caller_line": 3,
								"caller_symbol": "pkg/caller#handle().",
								"callee_file": "callee.py", "callee_line": 1,
								"callee_symbol": "pkg/callee#callee().",
							},
						},
					},
				}},
				{FactKind: "file", Payload: map[string]any{
					"repo_id": "repo-1", "relative_path": "callee.py",
					"parsed_file_data": map[string]any{
						"path": "callee.py",
						"functions": []any{
							map[string]any{"name": "callee", "line_number": 1, "uid": "uid:callee"},
						},
					},
				}},
			},
		},
		EdgeWriter:           writer,
		CanonicalNodeChecker: nil, // backwards-compatible: no checker
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-1",
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		Domain:       DomainCodeCallMaterialization,
		EnqueuedAt:   now,
		AvailableAt:  now,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	if result.CanonicalWrites == 0 {
		t.Fatal("result.CanonicalWrites = 0, want > 0 when checker is nil (backwards compat)")
	}
}

func TestCodeCallMaterializationHandlerProceedsWhenCheckerErrors(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 14, 12, 0, 0, 0, time.UTC)
	writer := &recordingCodeCallEdgeWriter{}
	handler := CodeCallMaterializationHandler{
		FactLoader: &stubFactLoader{
			envelopes: []facts.Envelope{
				{FactKind: "repository", Payload: map[string]any{"repo_id": "repo-1"}},
				{FactKind: "file", Payload: map[string]any{
					"repo_id": "repo-1", "relative_path": "caller.py",
					"parsed_file_data": map[string]any{
						"path": "caller.py",
						"functions": []any{
							map[string]any{"name": "handle", "line_number": 3, "uid": "uid:caller"},
						},
						"function_calls_scip": []any{
							map[string]any{
								"caller_file": "caller.py", "caller_line": 3,
								"caller_symbol": "pkg/caller#handle().",
								"callee_file": "callee.py", "callee_line": 1,
								"callee_symbol": "pkg/callee#callee().",
							},
						},
					},
				}},
				{FactKind: "file", Payload: map[string]any{
					"repo_id": "repo-1", "relative_path": "callee.py",
					"parsed_file_data": map[string]any{
						"path": "callee.py",
						"functions": []any{
							map[string]any{"name": "callee", "line_number": 1, "uid": "uid:callee"},
						},
					},
				}},
			},
		},
		EdgeWriter:           writer,
		CanonicalNodeChecker: &fakeCanonicalNodeChecker{exists: false, err: fmt.Errorf("neo4j unavailable")},
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-1",
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		Domain:       DomainCodeCallMaterialization,
		EnqueuedAt:   now,
		AvailableAt:  now,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}
	// On checker error, should proceed conservatively (not skip)
	if result.CanonicalWrites == 0 {
		t.Fatal("result.CanonicalWrites = 0, want > 0 when checker errors (conservative)")
	}
}

type recordingCodeCallEdgeWriter struct {
	retractDomain         string
	retractEvidenceSource string
	retractRows           []SharedProjectionIntentRow
	writeDomain           string
	writeEvidenceSource   string
	writeRows             []SharedProjectionIntentRow
}

func (r *recordingCodeCallEdgeWriter) RetractEdges(
	_ context.Context,
	domain string,
	rows []SharedProjectionIntentRow,
	evidenceSource string,
) error {
	r.retractDomain = domain
	r.retractEvidenceSource = evidenceSource
	r.retractRows = append(r.retractRows, rows...)
	return nil
}

func (r *recordingCodeCallEdgeWriter) WriteEdges(
	_ context.Context,
	domain string,
	rows []SharedProjectionIntentRow,
	evidenceSource string,
) error {
	r.writeDomain = domain
	r.writeEvidenceSource = evidenceSource
	r.writeRows = append(r.writeRows, rows...)
	return nil
}

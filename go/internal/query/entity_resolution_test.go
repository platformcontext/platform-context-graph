package query

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type resolvingContentStore struct {
	fakePortContentStore
	matches []EntityContent
}

func (s resolvingContentStore) SearchEntitiesByName(
	_ context.Context,
	repoID string,
	entityType string,
	name string,
	limit int,
) ([]EntityContent, error) {
	return append([]EntityContent(nil), s.matches...), nil
}

func TestResolveExactGraphEntityCandidatePrefersUniqueNonTestMatch(t *testing.T) {
	t.Parallel()

	reader := resolvingContentStore{
		matches: []EntityContent{
			{
				EntityID:     "content-entity:test",
				RepoID:       "repo-1",
				RelativePath: "go/internal/query/code_relationships_test.go",
				EntityType:   "Function",
				EntityName:   "handleRelationships",
				StartLine:    40,
			},
			{
				EntityID:     "content-entity:impl",
				RepoID:       "repo-1",
				RelativePath: "go/internal/query/code_relationships.go",
				EntityType:   "Function",
				EntityName:   "handleRelationships",
				StartLine:    22,
			},
		},
	}

	got, err := resolveExactGraphEntityCandidate(context.Background(), reader, "repo-1", "handleRelationships")
	if err != nil {
		t.Fatalf("resolveExactGraphEntityCandidate() error = %v, want nil", err)
	}
	if got == nil {
		t.Fatal("resolveExactGraphEntityCandidate() = nil, want non-nil")
	}
	if got.EntityID != "content-entity:impl" {
		t.Fatalf("resolveExactGraphEntityCandidate().EntityID = %q, want %q", got.EntityID, "content-entity:impl")
	}
}

func TestResolveExactGraphEntityCandidateRejectsAmbiguousNonTestMatches(t *testing.T) {
	t.Parallel()

	reader := resolvingContentStore{
		matches: []EntityContent{
			{
				EntityID:     "content-entity:one",
				RepoID:       "repo-1",
				RelativePath: "go/internal/query/code_relationships.go",
				EntityType:   "Function",
				EntityName:   "handleRelationships",
				StartLine:    22,
			},
			{
				EntityID:     "content-entity:two",
				RepoID:       "repo-1",
				RelativePath: "go/internal/query/code_other.go",
				EntityType:   "Function",
				EntityName:   "handleRelationships",
				StartLine:    44,
			},
		},
	}

	_, err := resolveExactGraphEntityCandidate(context.Background(), reader, "repo-1", "handleRelationships")
	if err == nil {
		t.Fatal("resolveExactGraphEntityCandidate() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), `entity name "handleRelationships" in repository "repo-1" matched multiple entities`) {
		t.Fatalf("resolveExactGraphEntityCandidate() error = %q, want ambiguity detail", err.Error())
	}
}

func TestHandleRelationshipsResolvesRepoScopedNameToNonTestEntityID(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if !strings.Contains(cypher, graphEntityIDPredicate("e", "$entity_id")) {
					t.Fatalf("cypher = %q, want bridged entity-id predicate", cypher)
				}
				if got, want := params["entity_id"], "content-entity:impl"; got != want {
					t.Fatalf("params[entity_id] = %#v, want %#v", got, want)
				}
				return map[string]any{
					"id":         "content-entity:impl",
					"name":       "handleRelationships",
					"labels":     []any{"Function"},
					"file_path":  "go/internal/query/code_relationships.go",
					"repo_id":    "repo-1",
					"repo_name":  "pcg",
					"language":   "go",
					"start_line": int64(22),
					"end_line":   int64(168),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"target_name": "transitiveRelationshipsGraphRow",
							"target_id":   "content-entity:callee",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
		Content: resolvingContentStore{
			matches: []EntityContent{
				{
					EntityID:     "content-entity:test",
					RepoID:       "repo-1",
					RelativePath: "go/internal/query/code_relationships_test.go",
					EntityType:   "Function",
					EntityName:   "handleRelationships",
					StartLine:    40,
				},
				{
					EntityID:     "content-entity:impl",
					RepoID:       "repo-1",
					RelativePath: "go/internal/query/code_relationships.go",
					EntityType:   "Function",
					EntityName:   "handleRelationships",
					StartLine:    22,
				},
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"name":"handleRelationships","repo_id":"repo-1","direction":"outgoing","relationship_type":"CALLS"}`),
	)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d body=%s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}
	if got, want := resp["entity_id"], "content-entity:impl"; got != want {
		t.Fatalf("resp[entity_id] = %#v, want %#v", got, want)
	}
}

func TestHandleCallChainResolvesRepoScopedNamesToNonTestEntityIDs(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if !strings.Contains(cypher, graphEntityIDPredicate("start", "$start_entity_id")) {
					t.Fatalf("cypher = %q, want bridged start entity-id predicate", cypher)
				}
				if !strings.Contains(cypher, graphEntityIDPredicate("end", "$end_entity_id")) {
					t.Fatalf("cypher = %q, want bridged end entity-id predicate", cypher)
				}
				if got, want := params["start_entity_id"], "content-entity:start-impl"; got != want {
					t.Fatalf("params[start_entity_id] = %#v, want %#v", got, want)
				}
				if got, want := params["end_entity_id"], "content-entity:end-impl"; got != want {
					t.Fatalf("params[end_entity_id] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"chain": []any{
							map[string]any{"id": "content-entity:start-impl", "name": "handleRelationships", "labels": []any{"Function"}},
							map[string]any{"id": "content-entity:end-impl", "name": "transitiveRelationshipsGraphResponse", "labels": []any{"Function"}},
						},
						"depth": int64(1),
					},
				}, nil
			},
		},
		Content: resolvingContentStore{
			matches: []EntityContent{
				{EntityID: "content-entity:test", RepoID: "repo-1", RelativePath: "go/internal/query/code_relationships_test.go", EntityType: "Function", EntityName: "handleRelationships", StartLine: 40},
				{EntityID: "content-entity:start-impl", RepoID: "repo-1", RelativePath: "go/internal/query/code_relationships.go", EntityType: "Function", EntityName: "handleRelationships", StartLine: 22},
				{EntityID: "content-entity:end-test", RepoID: "repo-1", RelativePath: "go/internal/query/code_call_graph_contract_test.go", EntityType: "Function", EntityName: "transitiveRelationshipsGraphResponse", StartLine: 10},
				{EntityID: "content-entity:end-impl", RepoID: "repo-1", RelativePath: "go/internal/query/code_relationships.go", EntityType: "Function", EntityName: "transitiveRelationshipsGraphResponse", StartLine: 250},
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/call-chain",
		bytes.NewBufferString(`{"start":"handleRelationships","end":"transitiveRelationshipsGraphResponse","repo_id":"repo-1","max_depth":4}`),
	)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d body=%s", got, want, w.Body.String())
	}
}

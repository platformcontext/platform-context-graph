package query

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestValidateReadOnlyCypher_RejectsMutationKeywords(t *testing.T) {
	cases := []struct {
		name  string
		query string
	}{
		{"CREATE", "CREATE (n:Node {name: 'test'})"},
		{"MERGE", "MERGE (n:Node {name: 'test'})"},
		{"DELETE", "MATCH (n) DELETE n"},
		{"DETACH", "MATCH (n) DETACH DELETE n"},
		{"SET", "MATCH (n) SET n.name = 'x'"},
		{"REMOVE", "MATCH (n) REMOVE n.name"},
		{"DROP", "DROP INDEX my_index"},
		{"CALL", "CALL db.labels()"},
		{"FOREACH", "FOREACH (x IN [1,2] | CREATE (n))"},
		{"LOAD CSV", "LOAD CSV FROM 'file:///x' AS row"},
		{"lowercase create", "match (n) create (m)"},
		{"mixed case", "Match (n) Merge (m)"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateReadOnlyCypher(tc.query)
			if err == nil {
				t.Errorf("expected rejection for query %q", tc.query)
			}
		})
	}
}

func TestValidateReadOnlyCypher_AllowsReadOnlyQueries(t *testing.T) {
	cases := []struct {
		name  string
		query string
	}{
		{"simple match", "MATCH (n) RETURN n LIMIT 10"},
		{"count nodes", "MATCH (n) RETURN count(n)"},
		{"relationship query", "MATCH (a)-[r]->(b) RETURN a, r, b"},
		{"with clause", "MATCH (n) WITH n.name AS name RETURN name"},
		{"optional match", "OPTIONAL MATCH (n) RETURN n"},
		{"where clause", "MATCH (n) WHERE n.name = 'test' RETURN n"},
		{"order by", "MATCH (n) RETURN n ORDER BY n.name"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateReadOnlyCypher(tc.query)
			if err != nil {
				t.Errorf("expected valid query %q to pass, got: %v", tc.query, err)
			}
		})
	}
}

func TestValidateReadOnlyCypher_RejectsLongQueries(t *testing.T) {
	long := strings.Repeat("MATCH (n) RETURN n ", 300)
	err := validateReadOnlyCypher(long)
	if err == nil {
		t.Error("expected rejection for excessively long query")
	}
}

func TestHandleCypherQuery_RejectsMutations(t *testing.T) {
	h := &CodeHandler{Neo4j: &stubGraphReader{}}

	body := `{"cypher_query": "CREATE (n:Node) RETURN n"}`
	req := httptest.NewRequest("POST", "/api/v0/code/cypher", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	h.handleCypherQuery(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestHandleCypherQuery_ExecutesReadOnlyQuery(t *testing.T) {
	stub := &stubGraphReader{
		rows: []map[string]any{{"count": 42}},
	}
	h := &CodeHandler{Neo4j: stub}

	body := `{"cypher_query": "MATCH (n) RETURN count(n) AS count"}`
	req := httptest.NewRequest("POST", "/api/v0/code/cypher", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	h.handleCypherQuery(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	results, ok := resp["results"].([]any)
	if !ok || len(results) != 1 {
		t.Errorf("expected 1 result row, got %v", resp["results"])
	}
}

func TestHandleVisualizeQuery_ReturnsURL(t *testing.T) {
	h := &CodeHandler{Neo4j: &stubGraphReader{}}

	body := `{"cypher_query": "MATCH (n) RETURN n LIMIT 10"}`
	req := httptest.NewRequest("POST", "/api/v0/code/visualize", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	h.handleVisualizeQuery(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	u, ok := resp["url"].(string)
	if !ok || !strings.Contains(u, "browser") {
		t.Errorf("expected Neo4j Browser URL, got %v", resp["url"])
	}
}

func TestHandleVisualizeQuery_RejectsMutations(t *testing.T) {
	h := &CodeHandler{Neo4j: &stubGraphReader{}}

	body := `{"cypher_query": "DELETE (n)"}`
	req := httptest.NewRequest("POST", "/api/v0/code/visualize", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	h.handleVisualizeQuery(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestHandleSearchBundles_ReturnsResults(t *testing.T) {
	stub := &stubGraphReader{
		rows: []map[string]any{
			{"name": "my-repo", "repo_id": "abc123"},
		},
	}
	h := &CodeHandler{Neo4j: stub}

	body := `{"query": "my-repo"}`
	req := httptest.NewRequest("POST", "/api/v0/code/bundles", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	h.handleSearchBundles(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	bundles, ok := resp["bundles"].([]any)
	if !ok || len(bundles) != 1 {
		t.Errorf("expected 1 bundle, got %v", resp["bundles"])
	}
}

// stubGraphReader is a test double for GraphReader.
type stubGraphReader struct {
	rows []map[string]any
	err  error
}

func (s *stubGraphReader) Run(_ context.Context, _ string, _ map[string]any) ([]map[string]any, error) {
	return s.rows, s.err
}

func (s *stubGraphReader) RunSingle(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
	if len(s.rows) == 0 {
		return nil, s.err
	}
	return s.rows[0], s.err
}

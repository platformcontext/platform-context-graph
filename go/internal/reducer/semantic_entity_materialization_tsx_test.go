package reducer

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestExtractSemanticEntityRowsIncludesTSXFunctionFragmentFacts(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/src/Screen.tsx",
			},
			Payload: map[string]any{
				"repo_id":                "repo-1",
				"entity_id":              "function-tsx-1",
				"relative_path":          "src/Screen.tsx",
				"entity_type":            "Function",
				"entity_name":            "Screen",
				"language":               "tsx",
				"start_line":             7,
				"end_line":               14,
				"jsx_fragment_shorthand": true,
			},
		},
	}

	repoIDs, rows := ExtractSemanticEntityRows(envelopes)
	if got, want := repoIDs, []string{"repo-1"}; len(got) != len(want) || got[0] != want[0] {
		t.Fatalf("ExtractSemanticEntityRows() repoIDs = %v, want %v", got, want)
	}
	if got, want := len(rows), 1; got != want {
		t.Fatalf("ExtractSemanticEntityRows() rows = %d, want %d", got, want)
	}

	row := rows[0]
	if got, want := row.EntityType, "Function"; got != want {
		t.Fatalf("row.EntityType = %q, want %q", got, want)
	}
	if got, want := row.Metadata["jsx_fragment_shorthand"], true; got != want {
		t.Fatalf("row.Metadata[jsx_fragment_shorthand] = %#v, want %#v", got, want)
	}
}

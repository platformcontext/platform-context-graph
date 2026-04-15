package reducer

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestExtractSemanticEntityRowsCarriesElixirProtocolMetadata(t *testing.T) {
	t.Parallel()

	repoIDs, rows := ExtractSemanticEntityRows([]facts.Envelope{
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/lib/demo/serializable.ex",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"relative_path": "lib/demo/serializable.ex",
				"entity_id":     "protocol-1",
				"entity_type":   "Protocol",
				"entity_name":   "Demo.Serializable",
				"language":      "elixir",
				"start_line":    1,
				"end_line":      3,
				"entity_metadata": map[string]any{
					"module_kind": "protocol",
				},
			},
		},
		{
			FactKind: "content_entity",
			SourceRef: facts.Ref{
				SourceURI: "/repo/lib/demo/serializable.ex",
			},
			Payload: map[string]any{
				"repo_id":       "repo-1",
				"relative_path": "lib/demo/serializable.ex",
				"entity_id":     "impl-1",
				"entity_type":   "ProtocolImplementation",
				"entity_name":   "Demo.Serializable",
				"language":      "elixir",
				"start_line":    5,
				"end_line":      8,
				"entity_metadata": map[string]any{
					"module_kind":     "protocol_implementation",
					"protocol":        "Demo.Serializable",
					"implemented_for": "Demo.Worker",
				},
			},
		},
	})

	if got, want := repoIDs, []string{"repo-1"}; len(got) != len(want) || got[0] != want[0] {
		t.Fatalf("ExtractSemanticEntityRows() repoIDs = %v, want %v", got, want)
	}
	if got, want := len(rows), 2; got != want {
		t.Fatalf("ExtractSemanticEntityRows() rows = %d, want %d", got, want)
	}

	if got, want := rows[0].EntityType, "Protocol"; got != want {
		t.Fatalf("rows[0].EntityType = %q, want %q", got, want)
	}
	if got, want := rows[0].Metadata["module_kind"], "protocol"; got != want {
		t.Fatalf("rows[0].Metadata[module_kind] = %#v, want %#v", got, want)
	}

	if got, want := rows[1].EntityType, "ProtocolImplementation"; got != want {
		t.Fatalf("rows[1].EntityType = %q, want %q", got, want)
	}
	if got, want := rows[1].Metadata["protocol"], "Demo.Serializable"; got != want {
		t.Fatalf("rows[1].Metadata[protocol] = %#v, want %#v", got, want)
	}
	if got, want := rows[1].Metadata["implemented_for"], "Demo.Worker"; got != want {
		t.Fatalf("rows[1].Metadata[implemented_for] = %#v, want %#v", got, want)
	}
}

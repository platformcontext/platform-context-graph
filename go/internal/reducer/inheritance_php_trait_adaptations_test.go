package reducer

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestInheritanceTraitOverrideTargetsParsesNamespacedMultiTargetInsteadof(t *testing.T) {
	t.Parallel()

	got := inheritanceTraitOverrideTargets(`Vendor\Features\Auditable::record insteadof Vendor\Features\Loggable, Vendor\Legacy\Traceable`)

	want := []string{"Loggable", "Traceable"}
	if len(got) != len(want) {
		t.Fatalf("len(got) = %d, want %d; got=%v", len(got), len(want), got)
	}
	for i, target := range want {
		if got[i] != target {
			t.Fatalf("got[%d] = %q, want %q (got=%v)", i, got[i], target, got)
		}
	}
}

func TestInheritanceTraitAliasTargetsParsesNamespacedAliasClause(t *testing.T) {
	t.Parallel()

	got := inheritanceTraitAliasTargets(`Vendor\Features\Loggable::record as private logRecord`)

	want := []string{"Loggable"}
	if len(got) != len(want) {
		t.Fatalf("len(got) = %d, want %d; got=%v", len(got), len(want), got)
	}
	for i, target := range want {
		if got[i] != target {
			t.Fatalf("got[%d] = %q, want %q (got=%v)", i, got[i], target, got)
		}
	}
}

func TestExtractInheritanceRowsMaterializesPHPTraitAdaptationOverrides(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactKind: "content_entity",
			Payload: map[string]any{
				"repo_id":     "repo-php",
				"entity_id":   "content-entity:loggable",
				"entity_type": "Trait",
				"entity_name": "Loggable",
			},
		},
		{
			FactKind: "content_entity",
			Payload: map[string]any{
				"repo_id":     "repo-php",
				"entity_id":   "content-entity:auditable",
				"entity_type": "Trait",
				"entity_name": "Auditable",
			},
		},
		{
			FactKind: "content_entity",
			Payload: map[string]any{
				"repo_id":     "repo-php",
				"entity_id":   "content-entity:traceable",
				"entity_type": "Trait",
				"entity_name": "Traceable",
			},
		},
		{
			FactKind: "content_entity",
			Payload: map[string]any{
				"repo_id":     "repo-php",
				"entity_id":   "content-entity:child",
				"entity_type": "Class",
				"entity_name": "Child",
				"entity_metadata": map[string]any{
					"bases": []any{"Loggable", "Auditable"},
					"trait_adaptations": []any{
						`Vendor\Features\Auditable::record insteadof Vendor\Features\Loggable, Vendor\Legacy\Traceable`,
						"Loggable::record as private logRecord",
					},
				},
			},
		},
	}

	repoIDs, rows := ExtractInheritanceRows(envelopes)
	if len(repoIDs) != 1 || repoIDs[0] != "repo-php" {
		t.Fatalf("repoIDs = %v, want [repo-php]", repoIDs)
	}

	var inheritsCount, overridesCount, aliasesCount int
	for _, row := range rows {
		switch row["relationship_type"] {
		case "INHERITS":
			inheritsCount++
		case "OVERRIDES":
			overridesCount++
			if got, want := row["parent_entity_id"], "content-entity:loggable"; got != want && got != "content-entity:traceable" {
				t.Fatalf("override parent_entity_id = %#v, want loggable or traceable", got)
			}
		case "ALIASES":
			aliasesCount++
			if got, want := row["parent_entity_id"], "content-entity:loggable"; got != want {
				t.Fatalf("alias parent_entity_id = %#v, want %#v", got, want)
			}
		}
	}

	if got, want := inheritsCount, 2; got != want {
		t.Fatalf("inheritsCount = %d, want %d", got, want)
	}
	if got, want := overridesCount, 2; got != want {
		t.Fatalf("overridesCount = %d, want %d", got, want)
	}
	if got, want := aliasesCount, 1; got != want {
		t.Fatalf("aliasesCount = %d, want %d", got, want)
	}
}

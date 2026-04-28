package reducer

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestSQLRelationshipHandlerUsesKindFilteredFactLoader(t *testing.T) {
	t.Parallel()

	loader := &recordingKindFactLoader{
		byKind: []facts.Envelope{
			{
				FactKind: "content_entity",
				Payload: map[string]any{
					"repo_id":     "repo-1",
					"entity_id":   "content-entity:table-1",
					"entity_type": "SqlTable",
					"entity_name": "public.users",
				},
			},
		},
		all: []facts.Envelope{
			{FactKind: "file"},
		},
	}
	writer := &recordingSQLRelEdgeWriter{}
	handler := SQLRelationshipMaterializationHandler{
		FactLoader:           loader,
		EdgeWriter:           writer,
		PriorGenerationCheck: func(context.Context, string, string) (bool, error) { return false, nil },
	}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-sql-kind-filter",
		ScopeID:      "scope-1",
		GenerationID: "generation-1",
		Domain:       DomainSQLRelationshipMaterialization,
		EnqueuedAt:   time.Now(),
		AvailableAt:  time.Now(),
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if loader.listFactsCalls != 0 {
		t.Fatalf("ListFacts() calls = %d, want 0", loader.listFactsCalls)
	}
	if got, want := strings.Join(loader.kindCalls[0], ","), "content_entity"; got != want {
		t.Fatalf("ListFactsByKind() kinds = %q, want %q", got, want)
	}
	if got, want := len(writer.retractRows), 0; got != want {
		t.Fatalf("retract count = %d, want %d", got, want)
	}
}

func TestSemanticEntityMaterializationHandlerUsesKindFilteredFactLoader(t *testing.T) {
	t.Parallel()

	loader := &recordingKindFactLoader{
		byKind: []facts.Envelope{
			{
				ScopeID:  "scope-1",
				FactKind: "repository",
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"source_run_id": "source-run-1",
				},
			},
			{
				FactKind: "content_entity",
				Payload: map[string]any{
					"repo_id":       "repo-1",
					"entity_id":     "entity-1",
					"entity_type":   "Module",
					"entity_name":   "main",
					"language":      "go",
					"relative_path": "main.go",
				},
				SourceRef: facts.Ref{SourceURI: "file:///repo/main.go"},
			},
		},
		all: []facts.Envelope{
			{FactKind: "file"},
		},
	}
	writer := &recordingSemanticEntityWriter{result: SemanticEntityWriteResult{CanonicalWrites: 1}}
	publisher := &recordingSemanticEntityPhasePublisher{}
	handler := SemanticEntityMaterializationHandler{
		FactLoader:           loader,
		Writer:               writer,
		PriorGenerationCheck: func(context.Context, string, string) (bool, error) { return false, nil },
		PhasePublisher:       publisher,
	}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-semantic-kind-filter",
		ScopeID:      "scope-1",
		GenerationID: "generation-1",
		Domain:       DomainSemanticEntityMaterialization,
		EnqueuedAt:   time.Now(),
		AvailableAt:  time.Now(),
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if loader.listFactsCalls != 0 {
		t.Fatalf("ListFacts() calls = %d, want 0", loader.listFactsCalls)
	}
	if got, want := strings.Join(loader.kindCalls[0], ","), "repository,content_entity"; got != want {
		t.Fatalf("ListFactsByKind() kinds = %q, want %q", got, want)
	}
	if got, want := len(writer.writes), 1; got != want {
		t.Fatalf("semantic writes = %d, want %d", got, want)
	}
	if got, want := len(publisher.calls), 1; got != want {
		t.Fatalf("phase publish calls = %d, want %d", got, want)
	}
}

type recordingKindFactLoader struct {
	all            []facts.Envelope
	byKind         []facts.Envelope
	listFactsCalls int
	kindCalls      [][]string
}

func (l *recordingKindFactLoader) ListFacts(
	context.Context,
	string,
	string,
) ([]facts.Envelope, error) {
	l.listFactsCalls++
	return append([]facts.Envelope(nil), l.all...), nil
}

func (l *recordingKindFactLoader) ListFactsByKind(
	_ context.Context,
	_ string,
	_ string,
	factKinds []string,
) ([]facts.Envelope, error) {
	l.kindCalls = append(l.kindCalls, append([]string(nil), factKinds...))
	return append([]facts.Envelope(nil), l.byKind...), nil
}

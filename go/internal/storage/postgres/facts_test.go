package postgres

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

func TestFactStoreUpsertFactsPersistsPayload(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{}
	store := NewFactStore(db)

	envelope := facts.Envelope{
		FactID:        "fact-1",
		ScopeID:       "scope-123",
		GenerationID:  "generation-456",
		FactKind:      "repository",
		StableFactKey: "repository:scope-123",
		ObservedAt:    time.Date(2026, time.April, 12, 8, 0, 0, 0, time.UTC),
		Payload:       map[string]any{"name": "platform-context-graph"},
		SourceRef: facts.Ref{
			SourceSystem:   "git",
			FactKey:        "fact-key",
			SourceURI:      "file:///repo/path",
			SourceRecordID: "record-123",
		},
	}

	if err := store.UpsertFacts(context.Background(), []facts.Envelope{envelope}); err != nil {
		t.Fatalf("UpsertFacts() error = %v, want nil", err)
	}

	if got, want := len(db.execs), 1; got != want {
		t.Fatalf("exec count = %d, want %d", got, want)
	}
	if !strings.Contains(db.execs[0].query, "INSERT INTO fact_records") {
		t.Fatalf("query = %q, want fact_records insert", db.execs[0].query)
	}
	payload, ok := db.execs[0].args[12].([]byte)
	if !ok || !strings.Contains(string(payload), "platform-context-graph") {
		t.Fatalf("payload arg = %#v, want json payload", db.execs[0].args[12])
	}
}

func TestFactStoreLoadFactsReturnsEnvelope(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{
			{
				rows: [][]any{{
					"fact-1",
					"scope-123",
					"generation-456",
					"repository",
					"repository:scope-123",
					"git",
					"fact-key",
					"file:///repo/path",
					"record-123",
					time.Date(2026, time.April, 12, 8, 0, 0, 0, time.UTC),
					false,
					[]byte(`{"name":"platform-context-graph"}`),
				}},
			},
		},
	}
	store := NewFactStore(db)

	work := projector.ScopeGenerationWork{
		Scope: scope.IngestionScope{ScopeID: "scope-123"},
		Generation: scope.ScopeGeneration{
			GenerationID: "generation-456",
		},
	}

	loaded, err := store.LoadFacts(context.Background(), work)
	if err != nil {
		t.Fatalf("LoadFacts() error = %v, want nil", err)
	}
	if got, want := len(loaded), 1; got != want {
		t.Fatalf("LoadFacts() len = %d, want %d", got, want)
	}
	if got, want := loaded[0].SourceRef.SourceSystem, "git"; got != want {
		t.Fatalf("LoadFacts()[0].SourceRef.SourceSystem = %q, want %q", got, want)
	}
	if got, want := loaded[0].Payload["name"], "platform-context-graph"; got != want {
		t.Fatalf("LoadFacts()[0].Payload[name] = %v, want %v", got, want)
	}
}

func TestFactStoreListFactsPropagatesQueryErrors(t *testing.T) {
	t.Parallel()

	db := &fakeExecQueryer{
		queryResponses: []queueFakeRows{{err: errors.New("boom")}},
	}
	store := NewFactStore(db)

	_, err := store.ListFacts(context.Background(), "scope-123", "generation-456")
	if err == nil {
		t.Fatal("ListFacts() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "list facts") {
		t.Fatalf("ListFacts() error = %q, want list facts context", err)
	}
}

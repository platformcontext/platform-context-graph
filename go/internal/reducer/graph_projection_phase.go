package reducer

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// GraphProjectionKeyspace identifies the concrete conflict domain for graph
// projection coordination.
type GraphProjectionKeyspace string

const (
	// GraphProjectionKeyspaceCodeEntitiesUID represents the Neo4j uniqueness
	// domain keyed by code entity uid values.
	GraphProjectionKeyspaceCodeEntitiesUID GraphProjectionKeyspace = "code_entities_uid"
	// GraphProjectionKeyspaceCrossRepoEvidence represents the reducer readiness
	// domain for deferred backward relationship evidence during bootstrap.
	GraphProjectionKeyspaceCrossRepoEvidence GraphProjectionKeyspace = "cross_repo_evidence"
)

// GraphProjectionPhase identifies one durable readiness milestone for a graph
// projection keyspace.
type GraphProjectionPhase string

const (
	// GraphProjectionPhaseCanonicalNodesCommitted is published after canonical
	// projector node writes commit successfully.
	GraphProjectionPhaseCanonicalNodesCommitted GraphProjectionPhase = "canonical_nodes_committed"
	// GraphProjectionPhaseSemanticNodesCommitted is published after semantic
	// entity reducer node writes commit successfully.
	GraphProjectionPhaseSemanticNodesCommitted GraphProjectionPhase = "semantic_nodes_committed"
	// GraphProjectionPhaseBackwardEvidenceCommitted is published after deferred
	// backward relationship evidence is durably committed for one
	// scope-generation slice.
	GraphProjectionPhaseBackwardEvidenceCommitted GraphProjectionPhase = "backward_evidence_committed"
)

// GraphProjectionPhaseKey identifies one bounded graph-write readiness slice.
type GraphProjectionPhaseKey struct {
	ScopeID          string
	AcceptanceUnitID string
	SourceRunID      string
	GenerationID     string
	Keyspace         GraphProjectionKeyspace
}

// GraphProjectionPhaseState captures one durable readiness publication.
type GraphProjectionPhaseState struct {
	Key         GraphProjectionPhaseKey
	Phase       GraphProjectionPhase
	CommittedAt time.Time
	UpdatedAt   time.Time
}

// Validate checks the bounded readiness identity contract.
func (k GraphProjectionPhaseKey) Validate() error {
	if strings.TrimSpace(k.ScopeID) == "" {
		return fmt.Errorf("scope_id must not be blank")
	}
	if strings.TrimSpace(k.AcceptanceUnitID) == "" {
		return fmt.Errorf("acceptance_unit_id must not be blank")
	}
	if strings.TrimSpace(k.SourceRunID) == "" {
		return fmt.Errorf("source_run_id must not be blank")
	}
	if strings.TrimSpace(k.GenerationID) == "" {
		return fmt.Errorf("generation_id must not be blank")
	}
	if strings.TrimSpace(string(k.Keyspace)) == "" {
		return fmt.Errorf("keyspace must not be blank")
	}
	return nil
}

// GraphProjectionReadinessLookup reports whether a bounded readiness slice has
// reached the requested phase. It returns (ready, found).
type GraphProjectionReadinessLookup func(key GraphProjectionPhaseKey, phase GraphProjectionPhase) (bool, bool)

// GraphProjectionReadinessPrefetch resolves readiness for a bounded set of keys
// and returns an in-memory lookup closure for the current cycle.
type GraphProjectionReadinessPrefetch func(ctx context.Context, keys []GraphProjectionPhaseKey, phase GraphProjectionPhase) (GraphProjectionReadinessLookup, error)

// GraphProjectionPhasePublisher persists graph-readiness publications.
type GraphProjectionPhasePublisher interface {
	PublishGraphProjectionPhases(context.Context, []GraphProjectionPhaseState) error
}

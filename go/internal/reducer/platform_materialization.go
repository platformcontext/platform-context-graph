package reducer

import (
	"context"
	"fmt"
	"strings"
)

// PlatformMaterializationWrite captures the bounded canonical reconciliation
// request for one platform materialization reducer intent.
type PlatformMaterializationWrite struct {
	IntentID        string
	ScopeID         string
	GenerationID    string
	SourceSystem    string
	Cause           string
	EntityKeys      []string
	RelatedScopeIDs []string
}

// PlatformMaterializationWriteResult captures the canonical platform
// materialization write outcome returned by the backend adapter.
type PlatformMaterializationWriteResult struct {
	CanonicalID     string
	CanonicalWrites int
	EvidenceSummary string
}

// PlatformMaterializationWriter persists one platform materialization request
// into a canonical reducer-owned target (Neo4j PROVISIONS_PLATFORM and
// RUNS_ON edges).
type PlatformMaterializationWriter interface {
	WritePlatformMaterialization(context.Context, PlatformMaterializationWrite) (PlatformMaterializationWriteResult, error)
}

// PlatformMaterializationHandler reduces one platform materialization intent
// into a bounded canonical write request. When FactLoader and
// InfrastructureMaterializer are set, the handler also writes
// PROVISIONS_PLATFORM edges to the canonical graph. When CrossRepoResolver
// is set, the handler also resolves cross-repo dependency edges from
// persisted evidence facts after platform materialization completes.
type PlatformMaterializationHandler struct {
	Writer                     PlatformMaterializationWriter
	FactLoader                 FactLoader
	InfrastructureMaterializer *InfrastructurePlatformMaterializer
	CrossRepoResolver          *CrossRepoRelationshipHandler
}

// Handle executes the platform materialization reduction path.
func (h PlatformMaterializationHandler) Handle(
	ctx context.Context,
	intent Intent,
) (Result, error) {
	if intent.Domain != DomainDeploymentMapping {
		return Result{}, fmt.Errorf(
			"platform materialization handler does not accept domain %q",
			intent.Domain,
		)
	}
	if h.Writer == nil {
		return Result{}, fmt.Errorf("platform materialization writer is required")
	}

	request, err := platformMaterializationWriteFromIntent(intent)
	if err != nil {
		return Result{}, err
	}

	writeResult, err := h.Writer.WritePlatformMaterialization(ctx, request)
	if err != nil {
		return Result{}, err
	}

	canonicalWrites := writeResult.CanonicalWrites

	// When both FactLoader and InfrastructureMaterializer are provided,
	// also write PROVISIONS_PLATFORM edges to the canonical graph.
	if h.FactLoader != nil && h.InfrastructureMaterializer != nil {
		facts, err := h.FactLoader.ListFacts(ctx, intent.ScopeID, intent.GenerationID)
		if err != nil {
			return Result{}, fmt.Errorf("load facts for infrastructure platform materialization: %w", err)
		}
		rows := ExtractInfrastructurePlatformRows(facts)
		if len(rows) > 0 {
			infraResult, err := h.InfrastructureMaterializer.Materialize(ctx, rows)
			if err != nil {
				return Result{}, fmt.Errorf("materialize infrastructure platforms: %w", err)
			}
			canonicalWrites += infraResult.PlatformEdgesWritten
		}
	}

	// When CrossRepoResolver is provided, resolve cross-repo dependency edges
	// from persisted evidence facts after platform materialization completes.
	if h.CrossRepoResolver != nil {
		crossRepoWrites, err := h.CrossRepoResolver.Resolve(ctx, intent.ScopeID, intent.GenerationID)
		if err != nil {
			return Result{}, fmt.Errorf("cross-repo relationship resolution: %w", err)
		}
		canonicalWrites += crossRepoWrites
	}

	evidenceSummary := strings.TrimSpace(writeResult.EvidenceSummary)
	if evidenceSummary == "" {
		evidenceSummary = fmt.Sprintf(
			"materialized %d platform key(s) across %d scope(s)",
			len(request.EntityKeys),
			len(request.RelatedScopeIDs),
		)
	}

	return Result{
		IntentID:        intent.IntentID,
		Domain:          DomainDeploymentMapping,
		Status:          ResultStatusSucceeded,
		EvidenceSummary: evidenceSummary,
		CanonicalWrites: canonicalWrites,
	}, nil
}

func platformMaterializationWriteFromIntent(intent Intent) (PlatformMaterializationWrite, error) {
	entityKeys := uniqueSortedStrings(intent.EntityKeys)
	if len(entityKeys) == 0 {
		return PlatformMaterializationWrite{}, fmt.Errorf(
			"platform materialization intent %q must include at least one entity key",
			intent.IntentID,
		)
	}

	relatedScopeIDs := uniqueSortedStrings(append(intent.RelatedScopeIDs, intent.ScopeID))
	if len(relatedScopeIDs) == 0 {
		return PlatformMaterializationWrite{}, fmt.Errorf(
			"platform materialization intent %q must include at least one related scope id",
			intent.IntentID,
		)
	}

	return PlatformMaterializationWrite{
		IntentID:        intent.IntentID,
		ScopeID:         intent.ScopeID,
		GenerationID:    intent.GenerationID,
		SourceSystem:    intent.SourceSystem,
		Cause:           intent.Cause,
		EntityKeys:      entityKeys,
		RelatedScopeIDs: relatedScopeIDs,
	}, nil
}

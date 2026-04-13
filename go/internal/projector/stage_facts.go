package projector

import (
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

// Fact kind constants after normalization (trailing "Fact" suffix stripped).
const (
	FactKindFileObserved         = "FileObserved"
	FactKindParsedEntityObserved = "ParsedEntityObserved"
	FactKindRepositoryObserved   = "RepositoryObserved"
)

// NormalizeFactKind returns a stable fact kind by stripping the legacy "Fact"
// suffix used during the transition period.
func NormalizeFactKind(kind string) string {
	return strings.TrimSuffix(kind, "Fact")
}

// FilterFileFacts returns file observation facts in stable insertion order
// with deduplication by FactID.
func FilterFileFacts(envelopes []facts.Envelope) []facts.Envelope {
	return filterFactsByKind(envelopes, FactKindFileObserved)
}

// FilterEntityFacts returns parsed-entity facts in stable insertion order
// with deduplication by FactID.
func FilterEntityFacts(envelopes []facts.Envelope) []facts.Envelope {
	return filterFactsByKind(envelopes, FactKindParsedEntityObserved)
}

// FilterRepositoryFacts returns repository observation facts in stable
// insertion order with deduplication by FactID.
func FilterRepositoryFacts(envelopes []facts.Envelope) []facts.Envelope {
	return filterFactsByKind(envelopes, FactKindRepositoryObserved)
}

func filterFactsByKind(envelopes []facts.Envelope, kind string) []facts.Envelope {
	seen := make(map[string]struct{}, len(envelopes))
	var result []facts.Envelope
	for i := range envelopes {
		if NormalizeFactKind(envelopes[i].FactKind) != kind {
			continue
		}
		if _, ok := seen[envelopes[i].FactID]; ok {
			continue
		}
		seen[envelopes[i].FactID] = struct{}{}
		result = append(result, envelopes[i])
	}
	return result
}

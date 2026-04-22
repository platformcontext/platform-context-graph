package query

import (
	"fmt"
	"net/http"
	"strings"
)

const EnvelopeMIMEType = "application/pcg.envelope+json"

type QueryProfile string

const (
	ProfileLocalLightweight QueryProfile = "local_lightweight"
	ProfileLocalFullStack   QueryProfile = "local_full_stack"
	ProfileProduction       QueryProfile = "production"
)

type TruthLevel string

const (
	TruthLevelExact    TruthLevel = "exact"
	TruthLevelDerived  TruthLevel = "derived"
	TruthLevelFallback TruthLevel = "fallback"
)

type TruthBasis string

const (
	TruthBasisAuthoritativeGraph TruthBasis = "authoritative_graph"
	TruthBasisSemanticFacts      TruthBasis = "semantic_facts"
	TruthBasisContentIndex       TruthBasis = "content_index"
	TruthBasisHybrid             TruthBasis = "hybrid"
)

type FreshnessState string

const (
	FreshnessFresh       FreshnessState = "fresh"
	FreshnessStale       FreshnessState = "stale"
	FreshnessBuilding    FreshnessState = "building"
	FreshnessUnavailable FreshnessState = "unavailable"
)

type TruthFreshness struct {
	State      FreshnessState `json:"state"`
	ObservedAt string         `json:"observed_at,omitempty"`
	Detail     string         `json:"detail,omitempty"`
}

type TruthEnvelope struct {
	Level      TruthLevel     `json:"level"`
	Capability string         `json:"capability,omitempty"`
	Profile    QueryProfile   `json:"profile,omitempty"`
	Basis      TruthBasis     `json:"basis,omitempty"`
	Freshness  TruthFreshness `json:"freshness"`
	Reason     string         `json:"reason,omitempty"`
}

type ErrorProfiles struct {
	Current  QueryProfile `json:"current,omitempty"`
	Required QueryProfile `json:"required,omitempty"`
}

type ErrorCode string

const (
	ErrorCodeUnsupportedCapability ErrorCode = "unsupported_capability"
	ErrorCodeBackendUnavailable    ErrorCode = "backend_unavailable"
	ErrorCodeIndexBuilding         ErrorCode = "index_building"
	ErrorCodeScopeNotFound         ErrorCode = "scope_not_found"
	ErrorCodeCapabilityDegraded    ErrorCode = "capability_degraded"
	ErrorCodeOverloaded            ErrorCode = "overloaded"
)

type ErrorEnvelope struct {
	Code       ErrorCode      `json:"code"`
	Message    string         `json:"message"`
	Capability string         `json:"capability,omitempty"`
	Profiles   *ErrorProfiles `json:"profiles,omitempty"`
}

type ResponseEnvelope struct {
	Data  any            `json:"data"`
	Truth *TruthEnvelope `json:"truth"`
	Error *ErrorEnvelope `json:"error"`
}

type capabilitySupport struct {
	LocalLightweightMax *TruthLevel
	LocalFullStackMax   *TruthLevel
	ProductionMax       *TruthLevel
	RequiredProfile     QueryProfile
}

var (
	truthExact   = TruthLevelExact
	truthDerived = TruthLevelDerived
)

var capabilityMatrix = map[string]capabilitySupport{
	"code_search.exact_symbol": {
		LocalLightweightMax: &truthExact,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"code_search.fuzzy_symbol": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthDerived,
		ProductionMax:       &truthDerived,
	},
	"code_search.variable_lookup": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"code_search.content_search": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthDerived,
		ProductionMax:       &truthDerived,
	},
	"symbol_graph.decorators": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"symbol_graph.argument_names": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"symbol_graph.class_methods": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"call_graph.direct_callers": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"call_graph.direct_callees": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"call_graph.transitive_callers": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"call_graph.transitive_callees": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"symbol_graph.imports": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"symbol_graph.inheritance": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
	},
	"code_quality.complexity": {
		LocalLightweightMax: &truthDerived,
		LocalFullStackMax:   &truthDerived,
		ProductionMax:       &truthDerived,
	},
	"call_graph.call_chain_path": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"code_quality.dead_code": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"platform_impact.deployment_chain": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"platform_impact.context_overview": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"platform_impact.blast_radius": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"platform_impact.change_surface": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"platform_impact.resource_to_code": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"platform_impact.dependency_path": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
	"platform_impact.environment_compare": {
		LocalLightweightMax: nil,
		LocalFullStackMax:   &truthExact,
		ProductionMax:       &truthExact,
		RequiredProfile:     ProfileLocalFullStack,
	},
}

func NormalizeQueryProfile(raw string) QueryProfile {
	profile, err := ParseQueryProfile(raw)
	if err != nil {
		return ""
	}
	return profile
}

func ParseQueryProfile(raw string) (QueryProfile, error) {
	switch QueryProfile(strings.TrimSpace(raw)) {
	case "":
		return "", nil
	case ProfileLocalLightweight:
		return ProfileLocalLightweight, nil
	case ProfileLocalFullStack:
		return ProfileLocalFullStack, nil
	case ProfileProduction:
		return ProfileProduction, nil
	default:
		return "", fmt.Errorf("invalid query profile %q", strings.TrimSpace(raw))
	}
}

func acceptsEnvelope(r *http.Request) bool {
	if r == nil {
		return false
	}
	accept := r.Header.Get("Accept")
	return strings.Contains(accept, EnvelopeMIMEType)
}

func maxTruthLevel(capability string, profile QueryProfile) *TruthLevel {
	support, ok := capabilityMatrix[capability]
	if !ok {
		return nil
	}
	switch profile {
	case ProfileLocalLightweight:
		return support.LocalLightweightMax
	case ProfileLocalFullStack:
		return support.LocalFullStackMax
	case ProfileProduction:
		return support.ProductionMax
	default:
		return support.ProductionMax
	}
}

func requiredProfile(capability string) QueryProfile {
	support, ok := capabilityMatrix[capability]
	if !ok || support.RequiredProfile == "" {
		return ProfileLocalFullStack
	}
	return support.RequiredProfile
}

func basisLevel(basis TruthBasis) TruthLevel {
	switch basis {
	case TruthBasisAuthoritativeGraph, TruthBasisSemanticFacts:
		return TruthLevelExact
	case TruthBasisContentIndex, TruthBasisHybrid:
		return TruthLevelDerived
	default:
		return TruthLevelFallback
	}
}

func minTruthLevel(a, b TruthLevel) TruthLevel {
	rank := map[TruthLevel]int{
		TruthLevelExact:    3,
		TruthLevelDerived:  2,
		TruthLevelFallback: 1,
	}
	if rank[a] <= rank[b] {
		return a
	}
	return b
}

func BuildTruthEnvelope(profile QueryProfile, capability string, basis TruthBasis, reason string) *TruthEnvelope {
	if _, ok := capabilityMatrix[capability]; !ok {
		panic(fmt.Sprintf("query capability %q missing from capability matrix", capability))
	}
	basis = normalizeTruthBasis(profile, basis)
	maxLevel := maxTruthLevel(capability, profile)
	level := basisLevel(basis)
	if maxLevel != nil {
		level = minTruthLevel(level, *maxLevel)
	}
	return &TruthEnvelope{
		Level:      level,
		Capability: capability,
		Profile:    profile,
		Basis:      basis,
		Freshness:  TruthFreshness{State: FreshnessFresh},
		Reason:     reason,
	}
}

func normalizeTruthBasis(profile QueryProfile, basis TruthBasis) TruthBasis {
	if profile == ProfileLocalLightweight && basis == TruthBasisAuthoritativeGraph {
		return TruthBasisHybrid
	}
	return basis
}

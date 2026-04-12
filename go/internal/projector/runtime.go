package projector

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

// Runtime projects one scope generation at a time into source-local graph and
// content materializations, then emits durable reducer intents for follow-up.
type Runtime struct {
	GraphWriter   graph.Writer
	ContentWriter content.Writer
	IntentWriter  ReducerIntentWriter
}

// ReducerIntent captures one durable shared follow-up request.
type ReducerIntent struct {
	ScopeID      string
	GenerationID string
	Domain       string
	EntityKey    string
	Reason       string
	FactID       string
	SourceSystem string
}

// ScopeGenerationKey returns the durable scope-generation boundary.
func (i ReducerIntent) ScopeGenerationKey() string {
	return fmt.Sprintf("%s:%s", i.ScopeID, i.GenerationID)
}

// IntentResult summarizes the durable reducer-intent enqueue step.
type IntentResult struct {
	Count int
}

// ReducerIntentWriter is the narrow durable queue contract for reducer follow-up.
type ReducerIntentWriter interface {
	Enqueue(context.Context, []ReducerIntent) (IntentResult, error)
}

// Result captures the source-local projection outcome for one generation.
type Result struct {
	ScopeID      string
	GenerationID string
	Graph        graph.Result
	Content      content.Result
	Intents      IntentResult
}

// ScopeGenerationKey returns the durable scope-generation boundary.
func (r Result) ScopeGenerationKey() string {
	return fmt.Sprintf("%s:%s", r.ScopeID, r.GenerationID)
}

// TraceSpanName returns the primary stable projector span name.
func (Runtime) TraceSpanName() string {
	return telemetry.SpanProjectorRun
}

// TraceSpanNames returns the stable span set used by the projector runtime path.
func (Runtime) TraceSpanNames() []string {
	return []string{
		telemetry.SpanProjectorRun,
		telemetry.SpanReducerIntentEnqueue,
		telemetry.SpanCanonicalWrite,
	}
}

// Project materializes local truth for one validated scope generation.
func (r Runtime) Project(ctx context.Context, scopeValue scope.IngestionScope, generation scope.ScopeGeneration, inputFacts []facts.Envelope) (Result, error) {
	if err := generation.ValidateForScope(scopeValue); err != nil {
		return Result{}, err
	}

	projection, err := buildProjection(scopeValue, generation, inputFacts)
	if err != nil {
		return Result{}, err
	}

	result := Result{
		ScopeID:      scopeValue.ScopeID,
		GenerationID: generation.GenerationID,
	}

	if len(projection.graphMaterialization.Records) > 0 {
		if r.GraphWriter == nil {
			return Result{}, errors.New("graph writer is required when graph records are present")
		}
		graphResult, err := r.GraphWriter.Write(ctx, projection.graphMaterialization)
		if err != nil {
			return Result{}, fmt.Errorf("write graph materialization: %w", err)
		}
		result.Graph = graphResult
	}

	if len(projection.contentMaterialization.Records) > 0 {
		if r.ContentWriter == nil {
			return Result{}, errors.New("content writer is required when content records are present")
		}
		contentResult, err := r.ContentWriter.Write(ctx, projection.contentMaterialization)
		if err != nil {
			return Result{}, fmt.Errorf("write content materialization: %w", err)
		}
		result.Content = contentResult
	}

	if len(projection.reducerIntents) > 0 {
		if r.IntentWriter == nil {
			return Result{}, errors.New("reducer intent writer is required when reducer intents are present")
		}
		intentResult, err := r.IntentWriter.Enqueue(ctx, projection.reducerIntents)
		if err != nil {
			return Result{}, fmt.Errorf("enqueue reducer intents: %w", err)
		}
		result.Intents = intentResult
	}

	return result, nil
}

type projection struct {
	graphMaterialization   graph.Materialization
	contentMaterialization content.Materialization
	reducerIntents         []ReducerIntent
}

func buildProjection(scopeValue scope.IngestionScope, generation scope.ScopeGeneration, inputFacts []facts.Envelope) (projection, error) {
	graphMaterialization := graph.Materialization{
		ScopeID:      scopeValue.ScopeID,
		GenerationID: generation.GenerationID,
		SourceSystem: scopeValue.SourceSystem,
	}
	contentMaterialization := content.Materialization{
		RepoID:       scopeRepoID(scopeValue),
		ScopeID:      scopeValue.ScopeID,
		GenerationID: generation.GenerationID,
		SourceSystem: scopeValue.SourceSystem,
	}

	intents := make([]ReducerIntent, 0, len(inputFacts))
	for i := range inputFacts {
		fact := inputFacts[i].Clone()
		if err := validateFactBoundary(scopeValue, generation, fact); err != nil {
			return projection{}, err
		}

		if record, ok := buildGraphRecord(fact); ok {
			graphMaterialization.Records = append(graphMaterialization.Records, record)
		}
		if record, ok := buildContentRecord(fact); ok {
			contentMaterialization.Records = append(contentMaterialization.Records, record)
		}
		if intent, ok := buildReducerIntent(fact); ok {
			intents = append(intents, intent)
		}
	}

	sort.SliceStable(intents, func(i, j int) bool {
		left := intents[i]
		right := intents[j]
		if left.Domain != right.Domain {
			return left.Domain < right.Domain
		}
		if left.EntityKey != right.EntityKey {
			return left.EntityKey < right.EntityKey
		}
		return left.FactID < right.FactID
	})

	return projection{
		graphMaterialization:   graphMaterialization,
		contentMaterialization: contentMaterialization,
		reducerIntents:         intents,
	}, nil
}

func scopeRepoID(scopeValue scope.IngestionScope) string {
	if len(scopeValue.Metadata) == 0 {
		return ""
	}

	return strings.TrimSpace(scopeValue.Metadata["repo_id"])
}

func validateFactBoundary(scopeValue scope.IngestionScope, generation scope.ScopeGeneration, fact facts.Envelope) error {
	if fact.ScopeID != scopeValue.ScopeID {
		return fmt.Errorf("fact %q scope_id %q does not match scope %q", fact.FactID, fact.ScopeID, scopeValue.ScopeID)
	}
	if fact.GenerationID != generation.GenerationID {
		return fmt.Errorf("fact %q generation_id %q does not match generation %q", fact.FactID, fact.GenerationID, generation.GenerationID)
	}

	return nil
}

func buildGraphRecord(fact facts.Envelope) (graph.Record, bool) {
	graphID, ok := payloadString(fact.Payload, "graph_id")
	if !ok {
		return graph.Record{}, false
	}

	kind, _ := payloadString(fact.Payload, "graph_kind")
	if kind == "" {
		kind = fact.FactKind
	}

	return graph.Record{
		RecordID:   graphID,
		Kind:       kind,
		Deleted:    fact.IsTombstone,
		Attributes: payloadAttributes(fact.Payload, "graph_id", "graph_kind"),
	}, true
}

func buildContentRecord(fact facts.Envelope) (content.Record, bool) {
	path, ok := payloadString(fact.Payload, "content_path")
	if !ok {
		return content.Record{}, false
	}

	body, _ := payloadString(fact.Payload, "content_body")
	digest, _ := payloadString(fact.Payload, "content_digest")

	return content.Record{
		Path:     path,
		Body:     body,
		Digest:   digest,
		Deleted:  fact.IsTombstone,
		Metadata: payloadAttributes(fact.Payload, "content_path", "content_body", "content_digest"),
	}, true
}

func buildReducerIntent(fact facts.Envelope) (ReducerIntent, bool) {
	domain, ok := payloadString(fact.Payload, "reducer_domain")
	if !ok {
		domain, ok = payloadString(fact.Payload, "shared_domain")
		if !ok {
			return ReducerIntent{}, false
		}
	}

	entityKey, _ := payloadString(fact.Payload, "entity_key")
	reason, _ := payloadString(fact.Payload, "reason")

	return ReducerIntent{
		ScopeID:      fact.ScopeID,
		GenerationID: fact.GenerationID,
		Domain:       domain,
		EntityKey:    entityKey,
		Reason:       reason,
		FactID:       fact.FactID,
		SourceSystem: fact.SourceRef.SourceSystem,
	}, true
}

func payloadAttributes(payload map[string]any, excluded ...string) map[string]string {
	if len(payload) == 0 {
		return nil
	}

	skip := make(map[string]struct{}, len(excluded))
	for _, key := range excluded {
		skip[key] = struct{}{}
	}

	attributes := make(map[string]string, len(payload))
	for key, value := range payload {
		if _, ok := skip[key]; ok {
			continue
		}
		if text, ok := asString(value); ok {
			attributes[key] = text
		}
	}

	if len(attributes) == 0 {
		return nil
	}

	return attributes
}

func payloadString(payload map[string]any, key string) (string, bool) {
	if len(payload) == 0 {
		return "", false
	}

	value, ok := payload[key]
	if !ok {
		return "", false
	}

	text, ok := asString(value)
	if !ok {
		return "", false
	}

	text = strings.TrimSpace(text)
	if text == "" {
		return "", false
	}

	return text, true
}

func asString(value any) (string, bool) {
	switch typed := value.(type) {
	case string:
		return typed, true
	case fmt.Stringer:
		return typed.String(), true
	default:
		return "", false
	}
}

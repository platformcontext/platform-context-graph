package projector

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

type Runtime struct {
	GraphWriter   graph.Writer
	ContentWriter content.Writer
	IntentWriter  ReducerIntentWriter
	RetryInjector RetryInjector
	Tracer        trace.Tracer           // optional
	Instruments   *telemetry.Instruments // optional
}

type ReducerIntent struct {
	ScopeID      string
	GenerationID string
	Domain       reducer.Domain
	EntityKey    string
	Reason       string
	FactID       string
	SourceSystem string
}

func (i ReducerIntent) ScopeGenerationKey() string {
	return fmt.Sprintf("%s:%s", i.ScopeID, i.GenerationID)
}

type IntentResult struct {
	Count int
}

type ReducerIntentWriter interface {
	Enqueue(context.Context, []ReducerIntent) (IntentResult, error)
}

type Result struct {
	ScopeID      string
	GenerationID string
	Graph        graph.Result
	Content      content.Result
	Intents      IntentResult
}

func (r Result) ScopeGenerationKey() string {
	return fmt.Sprintf("%s:%s", r.ScopeID, r.GenerationID)
}

func (Runtime) TraceSpanName() string {
	return telemetry.SpanProjectorRun
}

func (Runtime) TraceSpanNames() []string {
	return []string{
		telemetry.SpanProjectorRun,
		telemetry.SpanReducerIntentEnqueue,
		telemetry.SpanCanonicalWrite,
	}
}

func (r Runtime) Project(ctx context.Context, scopeValue scope.IngestionScope, generation scope.ScopeGeneration, inputFacts []facts.Envelope) (Result, error) {
	if err := generation.ValidateForScope(scopeValue); err != nil {
		return Result{}, err
	}

	buildStart := time.Now()
	projection, err := buildProjection(scopeValue, generation, inputFacts)
	if err != nil {
		return Result{}, err
	}
	if r.Instruments != nil {
		r.Instruments.ProjectorStageDuration.Record(ctx, time.Since(buildStart).Seconds(), metric.WithAttributes(
			telemetry.AttrScopeID(scopeValue.ScopeID),
			attribute.String("stage", "build_projection"),
		))
	}

	result := Result{
		ScopeID:      scopeValue.ScopeID,
		GenerationID: generation.GenerationID,
	}

	if r.RetryInjector != nil {
		if err := r.RetryInjector.MaybeFail(scopeValue, generation); err != nil {
			return Result{}, err
		}
	}

	if len(projection.graphMaterialization.Records) > 0 {
		if r.GraphWriter == nil {
			return Result{}, errors.New("graph writer is required when graph records are present")
		}

		writeStart := time.Now()
		if r.Tracer != nil {
			var writeSpan trace.Span
			ctx, writeSpan = r.Tracer.Start(ctx, telemetry.SpanCanonicalWrite)
			defer writeSpan.End()
		}

		graphResult, err := r.GraphWriter.Write(ctx, projection.graphMaterialization)
		if err != nil {
			return Result{}, fmt.Errorf("write graph materialization: %w", err)
		}

		if r.Instruments != nil {
			r.Instruments.CanonicalWriteDuration.Record(ctx, time.Since(writeStart).Seconds(), metric.WithAttributes(
				telemetry.AttrScopeID(scopeValue.ScopeID),
			))
			r.Instruments.CanonicalWrites.Add(ctx, 1, metric.WithAttributes(
				telemetry.AttrScopeID(scopeValue.ScopeID),
			))
			r.Instruments.ProjectorStageDuration.Record(ctx, time.Since(writeStart).Seconds(), metric.WithAttributes(
				telemetry.AttrScopeID(scopeValue.ScopeID),
				attribute.String("stage", "graph_write"),
			))
		}

		result.Graph = graphResult
	}

	if len(projection.contentMaterialization.Records) > 0 || len(projection.contentMaterialization.Entities) > 0 {
		if r.ContentWriter == nil {
			return Result{}, errors.New("content writer is required when content rows are present")
		}

		contentStart := time.Now()
		contentResult, err := r.ContentWriter.Write(ctx, projection.contentMaterialization)
		if err != nil {
			return Result{}, fmt.Errorf("write content materialization: %w", err)
		}
		if r.Instruments != nil {
			r.Instruments.ProjectorStageDuration.Record(ctx, time.Since(contentStart).Seconds(), metric.WithAttributes(
				telemetry.AttrScopeID(scopeValue.ScopeID),
				attribute.String("stage", "content_write"),
			))
		}

		result.Content = contentResult
	}

	if len(projection.reducerIntents) > 0 {
		if r.IntentWriter == nil {
			return Result{}, errors.New("reducer intent writer is required when reducer intents are present")
		}

		enqueueStart := time.Now()
		if r.Tracer != nil {
			var enqueueSpan trace.Span
			ctx, enqueueSpan = r.Tracer.Start(ctx, telemetry.SpanReducerIntentEnqueue)
			defer enqueueSpan.End()
		}

		intentResult, err := r.IntentWriter.Enqueue(ctx, projection.reducerIntents)
		if err != nil {
			return Result{}, fmt.Errorf("enqueue reducer intents: %w", err)
		}

		if r.Instruments != nil {
			duration := time.Since(enqueueStart).Seconds()
			r.Instruments.ProjectorStageDuration.Record(ctx, duration, metric.WithAttributes(
				telemetry.AttrScopeID(scopeValue.ScopeID),
				attribute.String("stage", "intent_enqueue"),
			))
			r.Instruments.ReducerIntentsEnqueued.Add(ctx, int64(len(projection.reducerIntents)), metric.WithAttributes(
				telemetry.AttrScopeID(scopeValue.ScopeID),
			))
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
		if entity, ok := buildContentEntityRecord(contentMaterialization.RepoID, fact); ok {
			contentMaterialization.Entities = append(contentMaterialization.Entities, entity)
		}
		if intent, ok := buildSemanticEntityReducerIntent(fact); ok {
			intents = append(intents, intent)
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
	if !payloadHasKey(fact.Payload, "content_body") && !payloadHasKey(fact.Payload, "content_digest") {
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

func buildContentEntityRecord(repoID string, fact facts.Envelope) (content.EntityRecord, bool) {
	relativePath, ok := payloadString(fact.Payload, "content_path")
	if !ok {
		relativePath, ok = payloadString(fact.Payload, "relative_path")
	}
	if !ok {
		relativePath, ok = payloadString(fact.Payload, "path")
	}
	if !ok {
		return content.EntityRecord{}, false
	}

	entityType, ok := payloadString(fact.Payload, "entity_kind")
	if !ok {
		entityType, ok = payloadString(fact.Payload, "entity_type")
	}
	if !ok {
		entityType, ok = payloadString(fact.Payload, "sql_entity_type")
	}
	if !ok {
		entityType = fact.FactKind
	}
	if strings.TrimSpace(entityType) == "" {
		return content.EntityRecord{}, false
	}

	entityName, ok := payloadString(fact.Payload, "entity_name")
	if !ok {
		entityName, ok = payloadString(fact.Payload, "name")
	}
	if !ok {
		return content.EntityRecord{}, false
	}

	startLine, ok := payloadInt(fact.Payload, "start_line")
	if !ok {
		startLine, ok = payloadInt(fact.Payload, "line_number")
	}
	if !ok || startLine <= 0 {
		startLine = 1
	}

	endLine, ok := payloadInt(fact.Payload, "end_line")
	if !ok || endLine < startLine {
		endLine = startLine
	}

	startByte := payloadIntPtr(fact.Payload, "start_byte")
	endByte := payloadIntPtr(fact.Payload, "end_byte")
	language, _ := payloadString(fact.Payload, "language")
	if language == "" {
		language, _ = payloadString(fact.Payload, "lang")
	}
	artifactType, _ := payloadString(fact.Payload, "artifact_type")
	templateDialect, _ := payloadString(fact.Payload, "template_dialect")
	iacRelevant := payloadBoolPtr(fact.Payload, "iac_relevant")
	entityID, ok := payloadString(fact.Payload, "entity_id")
	if !ok {
		entityID = content.CanonicalEntityID(repoID, relativePath, entityType, entityName, startLine)
	}
	sourceCache, _ := payloadString(fact.Payload, "source_cache")

	return content.EntityRecord{
		EntityID:        entityID,
		Path:            relativePath,
		EntityType:      entityType,
		EntityName:      entityName,
		StartLine:       startLine,
		EndLine:         endLine,
		StartByte:       startByte,
		EndByte:         endByte,
		Language:        language,
		ArtifactType:    artifactType,
		TemplateDialect: templateDialect,
		IACRelevant:     iacRelevant,
		SourceCache:     sourceCache,
		Metadata:        entityMetadataFromPayload(fact.Payload),
		Deleted:         fact.IsTombstone,
	}, true
}

func buildReducerIntent(fact facts.Envelope) (ReducerIntent, bool) {
	domainValue, ok := payloadString(fact.Payload, "reducer_domain")
	if !ok {
		domainValue, ok = payloadString(fact.Payload, "shared_domain")
		if !ok {
			return ReducerIntent{}, false
		}
	}
	domain, err := reducer.ParseDomain(domainValue)
	if err != nil {
		return ReducerIntent{}, false
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

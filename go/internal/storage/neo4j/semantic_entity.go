package neo4j

import (
	"context"
	"fmt"
	"sort"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

const (
	semanticEntityEvidenceSource = "parser/semantic-entities"

	semanticAnnotationUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Annotation {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.kind = row.kind,
    n.target_kind = row.target_kind,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticTypedefUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Typedef {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.type = row.type,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticTypeAliasUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:TypeAlias {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.type_alias_kind = row.type_alias_kind,
    n.type_parameters = row.type_parameters,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticTypeAnnotationUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:TypeAnnotation {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.annotation_kind = row.annotation_kind,
    n.context = row.context,
    n.type = row.type,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticComponentUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Component {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.framework = row.framework,
    n.jsx_fragment_shorthand = row.jsx_fragment_shorthand,
    n.component_type_assertion = row.component_type_assertion,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticImplBlockUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:ImplBlock {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.kind = row.kind,
    n.trait = row.trait,
    n.target = row.target,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticProtocolUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Protocol {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.module_kind = row.module_kind,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticProtocolImplementationUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:ProtocolImplementation {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.module_kind = row.module_kind,
    n.protocol = row.protocol,
    n.implemented_for = row.implemented_for,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticVariableUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Variable {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.attribute_kind = row.attribute_kind,
    n.value = row.value,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticModuleUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Module {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.module_kind = row.module_kind,
    n.declaration_merge_group = row.declaration_merge_group,
    n.declaration_merge_count = row.declaration_merge_count,
    n.declaration_merge_kinds = row.declaration_merge_kinds,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticFunctionUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Function {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.impl_context = row.impl_context,
    n.docstring = row.docstring,
    n.method_kind = row.method_kind,
    n.annotation_kind = row.annotation_kind,
    n.context = row.context,
    n.jsx_fragment_shorthand = row.jsx_fragment_shorthand,
    n.decorators = row.decorators,
    n.async = row.async,
    n.semantic_kind = coalesce(row.semantic_kind, row.entity_type),
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`
	semanticRustImplBlockOwnershipCypher = `UNWIND $rows AS row
MATCH (impl:ImplBlock {uid: row.impl_block_id})
MATCH (fn:Function {uid: row.function_id})
MERGE (impl)-[:CONTAINS]->(fn)`

	semanticEntityRetractCypher = `MATCH (n:Annotation|Typedef|TypeAlias|TypeAnnotation|Component|Module|ImplBlock|Protocol|ProtocolImplementation|Variable|Function)
WHERE n.repo_id IN $repo_ids
  AND n.evidence_source = $evidence_source
DETACH DELETE n`
)

// SemanticEntityWriter writes Annotation, Typedef, TypeAlias, TypeAnnotation,
// Component, Module, ImplBlock, Protocol, ProtocolImplementation, Variable,
// and JavaScript callable Function semantic nodes into Neo4j.
type SemanticEntityWriter struct {
	executor  Executor
	BatchSize int
}

// NewSemanticEntityWriter returns a semantic-entity writer backed by the given Executor.
func NewSemanticEntityWriter(executor Executor, batchSize int) *SemanticEntityWriter {
	return &SemanticEntityWriter{executor: executor, BatchSize: batchSize}
}

func (w *SemanticEntityWriter) batchSize() int {
	if w.BatchSize <= 0 {
		return DefaultBatchSize
	}
	return w.BatchSize
}

// WriteSemanticEntities retracts stale semantic nodes for the touched
// repositories and upserts the current rows.
func (w *SemanticEntityWriter) WriteSemanticEntities(
	ctx context.Context,
	write reducer.SemanticEntityWrite,
) (reducer.SemanticEntityWriteResult, error) {
	if len(write.RepoIDs) == 0 && len(write.Rows) == 0 {
		return reducer.SemanticEntityWriteResult{}, nil
	}
	if w.executor == nil {
		return reducer.SemanticEntityWriteResult{}, fmt.Errorf("semantic entity writer executor is required")
	}

	repoIDs := uniqueSemanticRepoIDs(write.RepoIDs)

	if err := w.executor.Execute(ctx, Statement{
		Operation:  OperationCanonicalRetract,
		Cypher:     semanticEntityRetractCypher,
		Parameters: map[string]any{"repo_ids": repoIDs, "evidence_source": semanticEntityEvidenceSource},
	}); err != nil {
		return reducer.SemanticEntityWriteResult{}, err
	}

	rowsByLabel := map[string][]map[string]any{
		"Annotation":             nil,
		"Typedef":                nil,
		"TypeAlias":              nil,
		"TypeAnnotation":         nil,
		"Component":              nil,
		"Module":                 nil,
		"ImplBlock":              nil,
		"Protocol":               nil,
		"ProtocolImplementation": nil,
		"Variable":               nil,
		"Function":               nil,
	}
	for _, row := range write.Rows {
		rowMap, ok := buildSemanticEntityRowMap(row)
		if !ok {
			continue
		}
		rowsByLabel[row.EntityType] = append(rowsByLabel[row.EntityType], rowMap)
	}

	writes := 0
	for _, plan := range []struct {
		label  string
		cypher string
	}{
		{label: "Annotation", cypher: semanticAnnotationUpsertCypher},
		{label: "Typedef", cypher: semanticTypedefUpsertCypher},
		{label: "TypeAlias", cypher: semanticTypeAliasUpsertCypher},
		{label: "TypeAnnotation", cypher: semanticTypeAnnotationUpsertCypher},
		{label: "Component", cypher: semanticComponentUpsertCypher},
		{label: "Module", cypher: semanticModuleUpsertCypher},
		{label: "ImplBlock", cypher: semanticImplBlockUpsertCypher},
		{label: "Protocol", cypher: semanticProtocolUpsertCypher},
		{label: "ProtocolImplementation", cypher: semanticProtocolImplementationUpsertCypher},
		{label: "Variable", cypher: semanticVariableUpsertCypher},
		{label: "Function", cypher: semanticFunctionUpsertCypher},
	} {
		if err := w.executeSemanticEntityRows(ctx, plan.cypher, rowsByLabel[plan.label]); err != nil {
			return reducer.SemanticEntityWriteResult{}, err
		}
		writes += len(rowsByLabel[plan.label])
	}

	ownershipRows := buildRustImplBlockOwnershipRows(write.Rows)
	if len(ownershipRows) > 0 {
		if err := w.executeSemanticEntityRows(ctx, semanticRustImplBlockOwnershipCypher, ownershipRows); err != nil {
			return reducer.SemanticEntityWriteResult{}, err
		}
	}

	return reducer.SemanticEntityWriteResult{CanonicalWrites: writes}, nil
}

func (w *SemanticEntityWriter) executeSemanticEntityRows(ctx context.Context, cypher string, rows []map[string]any) error {
	if len(rows) == 0 {
		return nil
	}
	batchSize := w.batchSize()
	for start := 0; start < len(rows); start += batchSize {
		end := start + batchSize
		if end > len(rows) {
			end = len(rows)
		}
		if err := w.executor.Execute(ctx, Statement{
			Operation:  OperationCanonicalUpsert,
			Cypher:     cypher,
			Parameters: map[string]any{"rows": rows[start:end]},
		}); err != nil {
			return err
		}
	}
	return nil
}

func buildSemanticEntityRowMap(row reducer.SemanticEntityRow) (map[string]any, bool) {
	if row.RepoID == "" || row.EntityID == "" || row.EntityName == "" || row.FilePath == "" {
		return nil, false
	}
	if row.EntityType != "Annotation" && row.EntityType != "Typedef" && row.EntityType != "TypeAlias" &&
		row.EntityType != "TypeAnnotation" && row.EntityType != "Component" && row.EntityType != "Module" && row.EntityType != "ImplBlock" &&
		row.EntityType != "Protocol" && row.EntityType != "ProtocolImplementation" &&
		row.EntityType != "Variable" && row.EntityType != "Function" {
		return nil, false
	}
	if row.StartLine <= 0 {
		return nil, false
	}

	rowMap := map[string]any{
		"repo_id":         row.RepoID,
		"entity_id":       row.EntityID,
		"entity_type":     row.EntityType,
		"entity_name":     row.EntityName,
		"file_path":       row.FilePath,
		"relative_path":   row.RelativePath,
		"language":        row.Language,
		"start_line":      row.StartLine,
		"end_line":        row.EndLine,
		"evidence_source": semanticEntityEvidenceSource,
	}
	if row.Metadata != nil {
		if kind := semanticMetadataString(row.Metadata, "kind"); kind != "" {
			rowMap["kind"] = kind
		}
		if targetKind := semanticMetadataString(row.Metadata, "target_kind"); targetKind != "" {
			rowMap["target_kind"] = targetKind
		}
		if typ := semanticMetadataString(row.Metadata, "type"); typ != "" {
			rowMap["type"] = typ
		}
		if aliasKind := semanticMetadataString(row.Metadata, "type_alias_kind"); aliasKind != "" {
			rowMap["type_alias_kind"] = aliasKind
		}
		if typeParameters := semanticMetadataStringSlice(row.Metadata, "type_parameters"); len(typeParameters) > 0 {
			rowMap["type_parameters"] = typeParameters
		}
		if framework := semanticMetadataString(row.Metadata, "framework"); framework != "" {
			rowMap["framework"] = framework
		}
		if moduleKind := semanticMetadataString(row.Metadata, "module_kind"); moduleKind != "" {
			rowMap["module_kind"] = moduleKind
		}
		if declarationMergeGroup := semanticMetadataString(row.Metadata, "declaration_merge_group"); declarationMergeGroup != "" {
			rowMap["declaration_merge_group"] = declarationMergeGroup
		}
		if declarationMergeCount := semanticMetadataInt(row.Metadata, "declaration_merge_count"); declarationMergeCount > 0 {
			rowMap["declaration_merge_count"] = declarationMergeCount
		}
		if declarationMergeKinds := semanticMetadataStringSlice(row.Metadata, "declaration_merge_kinds"); len(declarationMergeKinds) > 0 {
			rowMap["declaration_merge_kinds"] = declarationMergeKinds
		}
		if jsxFragment := semanticMetadataBool(row.Metadata, "jsx_fragment_shorthand"); jsxFragment {
			rowMap["jsx_fragment_shorthand"] = true
		}
		if componentAssertion := semanticMetadataString(row.Metadata, "component_type_assertion"); componentAssertion != "" {
			rowMap["component_type_assertion"] = componentAssertion
		}
		if implContext := semanticMetadataString(row.Metadata, "impl_context"); implContext != "" {
			rowMap["impl_context"] = implContext
		}
		if trait := semanticMetadataString(row.Metadata, "trait"); trait != "" {
			rowMap["trait"] = trait
		}
		if target := semanticMetadataString(row.Metadata, "target"); target != "" {
			rowMap["target"] = target
		}
		if protocol := semanticMetadataString(row.Metadata, "protocol"); protocol != "" {
			rowMap["protocol"] = protocol
		}
		if implementedFor := semanticMetadataString(row.Metadata, "implemented_for"); implementedFor != "" {
			rowMap["implemented_for"] = implementedFor
		}
		if attributeKind := semanticMetadataString(row.Metadata, "attribute_kind"); attributeKind != "" {
			rowMap["attribute_kind"] = attributeKind
		}
		if value := semanticMetadataString(row.Metadata, "value"); value != "" {
			rowMap["value"] = value
		}
		if docstring := semanticMetadataString(row.Metadata, "docstring"); docstring != "" {
			rowMap["docstring"] = docstring
		}
		if methodKind := semanticMetadataString(row.Metadata, "method_kind"); methodKind != "" {
			rowMap["method_kind"] = methodKind
		}
		if annotationKind := semanticMetadataString(row.Metadata, "annotation_kind"); annotationKind != "" {
			rowMap["annotation_kind"] = annotationKind
		}
		if context := semanticMetadataString(row.Metadata, "context"); context != "" {
			rowMap["context"] = context
		}
		if jsxFragment := semanticMetadataBool(row.Metadata, "jsx_fragment_shorthand"); jsxFragment {
			rowMap["jsx_fragment_shorthand"] = true
		}
		if decorators := semanticMetadataStringSlice(row.Metadata, "decorators"); len(decorators) > 0 {
			rowMap["decorators"] = decorators
		}
		if async := semanticMetadataBool(row.Metadata, "async"); async {
			rowMap["async"] = true
		}
		if semanticKind := semanticMetadataString(row.Metadata, "semantic_kind"); semanticKind != "" {
			rowMap["semantic_kind"] = semanticKind
		}
	}
	return rowMap, true
}

func buildRustImplBlockOwnershipRows(rows []reducer.SemanticEntityRow) []map[string]any {
	if len(rows) == 0 {
		return nil
	}

	functionIDsByFileAndContext := make(map[string][]string)
	for _, row := range rows {
		if row.EntityType != "Function" {
			continue
		}
		implContext := semanticMetadataString(row.Metadata, "impl_context")
		if implContext == "" || row.FilePath == "" || row.EntityID == "" {
			continue
		}
		key := row.FilePath + "|" + implContext
		functionIDsByFileAndContext[key] = append(functionIDsByFileAndContext[key], row.EntityID)
	}

	seen := make(map[string]struct{})
	ownershipRows := make([]map[string]any, 0)
	for _, row := range rows {
		if row.EntityType != "ImplBlock" || row.FilePath == "" || row.EntityID == "" || row.EntityName == "" {
			continue
		}
		functionIDs := functionIDsByFileAndContext[row.FilePath+"|"+row.EntityName]
		for _, functionID := range functionIDs {
			dedupKey := row.EntityID + "->" + functionID
			if _, ok := seen[dedupKey]; ok {
				continue
			}
			seen[dedupKey] = struct{}{}
			ownershipRows = append(ownershipRows, map[string]any{
				"impl_block_id": row.EntityID,
				"function_id":   functionID,
			})
		}
	}

	return ownershipRows
}

func uniqueSemanticRepoIDs(repoIDs []string) []string {
	seen := make(map[string]struct{})
	unique := make([]string, 0, len(repoIDs))
	for _, repoID := range repoIDs {
		if repoID == "" {
			continue
		}
		if _, ok := seen[repoID]; ok {
			continue
		}
		seen[repoID] = struct{}{}
		unique = append(unique, repoID)
	}
	sort.Strings(unique)
	return unique
}

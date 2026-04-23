package neo4j

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
	n.component_wrapper_kind = row.component_wrapper_kind,
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
	    n.component_type_assertion = row.component_type_assertion,
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
    n.class_context = row.class_context,
    n.method_kind = row.method_kind,
    n.constructor_kind = row.constructor_kind,
    n.annotation_kind = row.annotation_kind,
    n.context = row.context,
    n.type_annotation_count = row.type_annotation_count,
    n.type_annotation_kinds = row.type_annotation_kinds,
    n.type_parameters = row.type_parameters,
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

func semanticEntitySingleRowUpsertCypher(label string) string {
	return "MATCH (f:File {path: $file_path})\n" +
		"MERGE (n:" + label + " {uid: $entity_id})\n" +
		"SET n += $properties\n" +
		"MERGE (f)-[:CONTAINS]->(n)"
}

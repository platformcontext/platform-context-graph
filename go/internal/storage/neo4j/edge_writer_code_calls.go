package neo4j

import "fmt"

// codeCallUpsertCypherForLabels narrows code-call node anchors when reducer
// intent payloads carry parser-owned source and target entity labels.
func codeCallUpsertCypherForLabels(sourceLabel string, targetLabel string) string {
	if !isCodeEntityLabel(sourceLabel) || !isCodeEntityLabel(targetLabel) {
		return batchCanonicalCodeCallUpsertCypher
	}
	return fmt.Sprintf(`UNWIND $rows AS row
MATCH (source:%s {uid: row.caller_entity_id})
MATCH (target:%s {uid: row.callee_entity_id})
MERGE (source)-[rel:CALLS]->(target)
SET rel.confidence = 0.95,
    rel.reason = 'Parser and symbol analysis resolved a code call edge',
    rel.evidence_source = row.evidence_source,
    rel.call_kind = row.call_kind`, sourceLabel, targetLabel)
}

// codeCallJSXReferenceCypherForLabels narrows JSX reference anchors while
// preserving the broad fallback for old or incomplete intent payloads.
func codeCallJSXReferenceCypherForLabels(sourceLabel string, targetLabel string) string {
	if !isCodeEntityLabel(sourceLabel) || !isCodeEntityLabel(targetLabel) {
		return batchCanonicalJSXComponentReferenceUpsertCypher
	}
	return fmt.Sprintf(`UNWIND $rows AS row
MATCH (source:%s {uid: row.caller_entity_id})
MATCH (target:%s {uid: row.callee_entity_id})
MERGE (source)-[rel:REFERENCES]->(target)
SET rel.confidence = 0.95,
    rel.reason = 'Parser and symbol analysis resolved a TSX component reference edge',
    rel.evidence_source = row.evidence_source,
    rel.call_kind = row.call_kind`, sourceLabel, targetLabel)
}

// codeCallMetaclassCypherForLabels narrows Python metaclass edge anchors when
// both entity labels are known from reducer extraction.
func codeCallMetaclassCypherForLabels(sourceLabel string, targetLabel string) string {
	if !isCodeEntityLabel(sourceLabel) || !isCodeEntityLabel(targetLabel) {
		return batchCanonicalMetaclassUpsertCypher
	}
	return fmt.Sprintf(`UNWIND $rows AS row
MATCH (source:%s {uid: row.source_entity_id})
MATCH (target:%s {uid: row.target_entity_id})
MERGE (source)-[rel:USES_METACLASS]->(target)
SET rel.confidence = 0.95,
    rel.reason = 'Parser and symbol analysis resolved a Python metaclass edge',
    rel.evidence_source = row.evidence_source,
    rel.relationship_type = row.relationship_type`, sourceLabel, targetLabel)
}

// isCodeEntityLabel whitelists labels that the code-call writer may splice
// into Cypher templates. Values come from parser/reducer metadata, not users.
func isCodeEntityLabel(label string) bool {
	switch label {
	case "Class", "File", "Function":
		return true
	default:
		return false
	}
}

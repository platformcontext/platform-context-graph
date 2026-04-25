package neo4j

const (
	// StatementMetadataPhaseKey tags a canonical-write statement with the
	// writer phase that produced it so narrower executors can preserve phase
	// ordering and diagnostics without parsing Cypher.
	StatementMetadataPhaseKey = "_pcg_phase"
	// StatementMetadataEntityLabelKey tags canonical entity statements with the
	// concrete entity label they are writing so backend-specific executors can
	// tune grouped execution without parsing summaries or Cypher text.
	StatementMetadataEntityLabelKey = "_pcg_entity_label"
	// StatementMetadataPhaseGroupModeKey tags a canonical-write statement with
	// group-execution handling hints such as execute-only singleton fallback.
	StatementMetadataPhaseGroupModeKey = "_pcg_phase_group_mode"
	// StatementMetadataSummaryKey carries a human-readable first-statement
	// summary used only for logging and error wrapping.
	StatementMetadataSummaryKey = "_pcg_statement_summary"

	// Canonical phase names form the narrow protocol between graph statement
	// builders and backend executors. Add a new phase only when repo-scale
	// evidence proves it needs different grouping, batching, or diagnostics
	// from the existing phases.
	CanonicalPhaseEntities          = "entities"
	CanonicalPhaseEntityContainment = "entity_containment"
	CanonicalPhaseFiles             = "files"
	PhaseGroupModeExecuteOnly       = "execute_only"
)

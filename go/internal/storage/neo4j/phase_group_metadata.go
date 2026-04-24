package neo4j

const (
	// StatementMetadataPhaseKey tags a canonical-write statement with the
	// writer phase that produced it so narrower executors can preserve phase
	// ordering and diagnostics without parsing Cypher.
	StatementMetadataPhaseKey = "_pcg_phase"
	// StatementMetadataPhaseGroupModeKey tags a canonical-write statement with
	// group-execution handling hints such as execute-only singleton fallback.
	StatementMetadataPhaseGroupModeKey = "_pcg_phase_group_mode"
	// StatementMetadataSummaryKey carries a human-readable first-statement
	// summary used only for logging and error wrapping.
	StatementMetadataSummaryKey = "_pcg_statement_summary"

	CanonicalPhaseEntities    = "entities"
	PhaseGroupModeExecuteOnly = "execute_only"
)

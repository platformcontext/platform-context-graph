package reducer

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"time"
)

// SharedProjectionDomain constants for the shared projection domains.
const (
	DomainPlatformInfra      = "platform_infra"
	DomainRepoDependency     = "repo_dependency"
	DomainWorkloadDependency = "workload_dependency"
	DomainCodeCalls          = "code_calls"
)

// SharedProjectionIntentRow is one durable shared-domain projection intent.
type SharedProjectionIntentRow struct {
	IntentID         string
	ProjectionDomain string
	PartitionKey     string
	RepositoryID     string
	SourceRunID      string
	GenerationID     string
	Payload          map[string]any
	CreatedAt        time.Time
	CompletedAt      *time.Time
}

// SharedProjectionIntentInput holds the parameters for building one
// deterministic shared projection intent row.
type SharedProjectionIntentInput struct {
	ProjectionDomain string
	PartitionKey     string
	RepositoryID     string
	SourceRunID      string
	GenerationID     string
	Payload          map[string]any
	CreatedAt        time.Time
}

// BuildSharedProjectionIntent builds one deterministic shared projection intent
// row. The intent ID is a SHA256 of the identity fields, matching the Python
// implementation exactly.
func BuildSharedProjectionIntent(input SharedProjectionIntentInput) SharedProjectionIntentRow {
	intentID := stableIntentID(map[string]string{
		"generation_id":     input.GenerationID,
		"partition_key":     input.PartitionKey,
		"projection_domain": input.ProjectionDomain,
		"repository_id":     input.RepositoryID,
		"source_run_id":     input.SourceRunID,
	})

	return SharedProjectionIntentRow{
		IntentID:         intentID,
		ProjectionDomain: input.ProjectionDomain,
		PartitionKey:     input.PartitionKey,
		RepositoryID:     input.RepositoryID,
		SourceRunID:      input.SourceRunID,
		GenerationID:     input.GenerationID,
		Payload:          input.Payload,
		CreatedAt:        input.CreatedAt,
		CompletedAt:      nil,
	}
}

// RowsForPartition returns intent rows whose partition key belongs to one
// worker partition.
func RowsForPartition(rows []SharedProjectionIntentRow, partitionID, partitionCount int) []SharedProjectionIntentRow {
	var result []SharedProjectionIntentRow
	for _, row := range rows {
		p, err := PartitionForKey(row.PartitionKey, partitionCount)
		if err != nil {
			continue
		}
		if p == partitionID {
			result = append(result, row)
		}
	}
	return result
}

// stableIntentID computes a deterministic intent identifier matching the Python
// _stable_intent_id function. It serializes the identity dict as compact
// JSON with sorted keys: {"identity":{...sorted fields...}}
func stableIntentID(identity map[string]string) string {
	// Build the identity object with sorted keys. Since json.Marshal sorts
	// map keys by default in Go, this produces the same output as Python's
	// json.dumps(sort_keys=True, separators=(",", ":")).
	wrapper := map[string]any{
		"identity": identity,
	}

	payload, err := json.Marshal(wrapper)
	if err != nil {
		// Identity fields are plain strings; marshal cannot fail.
		panic(fmt.Sprintf("marshal identity: %v", err))
	}

	digest := sha256.Sum256(payload)
	return fmt.Sprintf("%x", digest)
}

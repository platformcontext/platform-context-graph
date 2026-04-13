package projector

import (
	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
)

// FileStageResult captures the output of the file projection stage.
type FileStageResult struct {
	GraphRecords   []graph.Record
	ContentRecords []content.Record
	Entities       []content.EntityRecord
}

// ProjectFileStage projects file observation facts into graph records, content
// records, and content entity records. It deduplicates by fact ID.
func ProjectFileStage(repoID string, envelopes []facts.Envelope) FileStageResult {
	fileFacts := FilterFileFacts(envelopes)
	result := FileStageResult{}

	for i := range fileFacts {
		if record, ok := buildGraphRecord(fileFacts[i]); ok {
			result.GraphRecords = append(result.GraphRecords, record)
		}
		if record, ok := buildContentRecord(fileFacts[i]); ok {
			result.ContentRecords = append(result.ContentRecords, record)
		}
		if entity, ok := buildContentEntityRecord(repoID, fileFacts[i]); ok {
			result.Entities = append(result.Entities, entity)
		}
	}

	return result
}

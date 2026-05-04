package main

import (
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	sourcecypher "github.com/platformcontext/platform-context-graph/go/internal/storage/cypher"
)

// ingesterCanonicalWriterConfig captures backend-neutral canonical writer
// tuning after environment parsing has validated any backend-specific knobs.
type ingesterCanonicalWriterConfig struct {
	GraphBackend                      runtimecfg.GraphBackend
	FileBatchSize                     int
	EntityBatchSize                   int
	EntityLabelBatchSizes             map[string]int
	NornicDBBatchedEntityContainment  bool
	OrderedEntityLabelBatchSizeLabels []string
}

// configureIngesterCanonicalWriter applies the shared canonical writer shape
// used by official graph backends. NornicDB may opt into the latest-main
// batched containment experiment; otherwise Neo4j and NornicDB both use the
// file-scoped inline entity containment contract.
func configureIngesterCanonicalWriter(
	writer *sourcecypher.CanonicalNodeWriter,
	config ingesterCanonicalWriterConfig,
) *sourcecypher.CanonicalNodeWriter {
	if writer == nil {
		return nil
	}
	writer = writer.WithEntityContainmentInEntityUpsert()
	if config.EntityBatchSize > 0 {
		writer = writer.WithEntityBatchSize(config.EntityBatchSize)
	}
	if config.GraphBackend == runtimecfg.GraphBackendNornicDB {
		if config.FileBatchSize > 0 {
			writer = writer.WithFileBatchSize(config.FileBatchSize)
		}
		if config.NornicDBBatchedEntityContainment {
			writer = writer.WithBatchedEntityContainmentInEntityUpsert()
		}
		for _, label := range config.OrderedEntityLabelBatchSizeLabels {
			batchSize := config.EntityLabelBatchSizes[label]
			writer = writer.WithEntityLabelBatchSize(label, batchSize)
		}
	}
	return writer
}

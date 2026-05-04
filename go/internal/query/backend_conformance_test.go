package query

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/backendconformance"
)

func TestNeo4jReaderSatisfiesBackendConformanceGraphQuery(t *testing.T) {
	t.Parallel()

	var _ backendconformance.GraphQuery = (*Neo4jReader)(nil)
}

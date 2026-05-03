package query

import (
	"net/http"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/buildinfo"
)

// OpenAPISpec returns the OpenAPI 3.0 specification for the PCG Query API.
func OpenAPISpec() string {
	return strings.Replace(
		openAPISpecPrefix+
			openAPIPathsRepositories+
			openAPIPathsEntities+
			openAPIPathsCode+
			openAPIPathsIaC+
			openAPIPathsContent+
			openAPIPathsAdmin+
			openAPIPathsInfrastructure+
			openAPIPathsImpact+
			openAPIPathsEvidence+
			openAPIPathsStatusAndCompare+
			openAPIComponents,
		"__PCG_VERSION__",
		buildinfo.AppVersion(),
		1,
	)
}

// ServeOpenAPI returns an HTTP handler that serves the OpenAPI spec.
func ServeOpenAPI(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(OpenAPISpec()))
}

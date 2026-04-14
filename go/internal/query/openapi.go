package query

import "net/http"

// OpenAPISpec is the OpenAPI 3.0 specification for the PCG Query API.
const OpenAPISpec = openAPISpecPrefix +
	openAPIPathsRepositories +
	openAPIPathsEntities +
	openAPIPathsCode +
	openAPIPathsContent +
	openAPIPathsInfrastructure +
	openAPIPathsImpact +
	openAPIPathsStatusAndCompare +
	openAPIComponents

// ServeOpenAPI returns an HTTP handler that serves the OpenAPI spec.
func ServeOpenAPI(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(OpenAPISpec))
}

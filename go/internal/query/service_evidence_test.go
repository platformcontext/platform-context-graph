package query

import (
	"context"
	"errors"
	"slices"
	"testing"
)

func TestLoadServiceQueryEvidenceExtractsHostnamesEnvironmentsAndOpenAPISpecs(t *testing.T) {
	t.Parallel()

	reader := &stubServiceEvidenceReader{
		files: []FileContent{
			{RepoID: "repo-sample-service-api", RelativePath: "deploy/qa/ingress.yaml"},
			{RepoID: "repo-sample-service-api", RelativePath: "deploy/prod/ingress.yaml"},
			{RepoID: "repo-sample-service-api", RelativePath: "specs/index.yaml"},
			{RepoID: "repo-sample-service-api", RelativePath: "src/server.js"},
		},
		fileContent: map[string]string{
			"deploy/qa/ingress.yaml": `
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sample-service-api
spec:
  rules:
    - host: sample-service-api.qa.example.com
`,
			"deploy/prod/ingress.yaml": `
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sample-service-api
spec:
  rules:
    - host: sample-service-api.production.example.com
`,
			"specs/index.yaml": `
openapi: 3.0.3
info:
  title: Boats API
  version: v1
servers:
  - url: https://sample-service-api.qa.example.com
paths:
  /boats:
    get:
      operationId: listBoats
    post:
      operationId: createBoat
  /boats/{id}:
    get:
      operationId: getBoat
`,
			"src/server.js": `
const swaggerUi = require('swagger-ui-express')
app.use('/docs', swaggerUi.serve, swaggerUi.setup(spec))
`,
		},
	}

	evidence, err := loadServiceQueryEvidence(context.Background(), reader, "repo-sample-service-api", "sample-service-api")
	if err != nil {
		t.Fatalf("loadServiceQueryEvidence() error = %v, want nil", err)
	}

	gotHostnames := make([]string, 0, len(evidence.Hostnames))
	for _, row := range evidence.Hostnames {
		gotHostnames = append(gotHostnames, row.Hostname)
	}
	wantHostnames := []string{
		"sample-service-api.production.example.com",
		"sample-service-api.qa.example.com",
	}
	if !slices.Equal(gotHostnames, wantHostnames) {
		t.Fatalf("hostnames = %#v, want %#v", gotHostnames, wantHostnames)
	}

	gotEnvironments := make([]string, 0, len(evidence.Environments))
	for _, row := range evidence.Environments {
		gotEnvironments = append(gotEnvironments, row.Environment)
	}
	wantEnvironments := []string{"prod", "qa"}
	if !slices.Equal(gotEnvironments, wantEnvironments) {
		t.Fatalf("environments = %#v, want %#v", gotEnvironments, wantEnvironments)
	}

	if len(evidence.DocsRoutes) != 1 {
		t.Fatalf("len(docs_routes) = %d, want 1", len(evidence.DocsRoutes))
	}
	if got, want := evidence.DocsRoutes[0].Route, "/docs"; got != want {
		t.Fatalf("docs_routes[0].Route = %q, want %q", got, want)
	}

	if len(evidence.APISpecs) != 1 {
		t.Fatalf("len(api_specs) = %d, want 1", len(evidence.APISpecs))
	}
	spec := evidence.APISpecs[0]
	if !spec.Parsed {
		t.Fatal("api_specs[0].Parsed = false, want true")
	}
	if got, want := spec.RelativePath, "specs/index.yaml"; got != want {
		t.Fatalf("api_specs[0].RelativePath = %q, want %q", got, want)
	}
	if got, want := spec.SpecVersion, "3.0.3"; got != want {
		t.Fatalf("api_specs[0].SpecVersion = %q, want %q", got, want)
	}
	if got, want := spec.APIVersion, "v1"; got != want {
		t.Fatalf("api_specs[0].APIVersion = %q, want %q", got, want)
	}
	if got, want := spec.EndpointCount, 2; got != want {
		t.Fatalf("api_specs[0].EndpointCount = %d, want %d", got, want)
	}
	if got, want := spec.MethodCount, 3; got != want {
		t.Fatalf("api_specs[0].MethodCount = %d, want %d", got, want)
	}
	if got, want := spec.OperationIDCount, 3; got != want {
		t.Fatalf("api_specs[0].OperationIDCount = %d, want %d", got, want)
	}
	if got, want := spec.Hostnames, []string{"sample-service-api.qa.example.com"}; !slices.Equal(got, want) {
		t.Fatalf("api_specs[0].Hostnames = %#v, want %#v", got, want)
	}
}

func TestLoadServiceQueryEvidenceMarksJavaScriptSpecFilesAsSpecEvidence(t *testing.T) {
	t.Parallel()

	reader := &stubServiceEvidenceReader{
		files: []FileContent{
			{RepoID: "repo-sample-service-api", RelativePath: "src/spec.js"},
		},
		fileContent: map[string]string{
			"src/spec.js": `
module.exports = {
  openapi: '3.0.0',
}
`,
		},
	}

	evidence, err := loadServiceQueryEvidence(context.Background(), reader, "repo-sample-service-api", "sample-service-api")
	if err != nil {
		t.Fatalf("loadServiceQueryEvidence() error = %v, want nil", err)
	}
	if len(evidence.APISpecs) != 1 {
		t.Fatalf("len(api_specs) = %d, want 1", len(evidence.APISpecs))
	}
	if got, want := evidence.APISpecs[0].RelativePath, "src/spec.js"; got != want {
		t.Fatalf("api_specs[0].RelativePath = %q, want %q", got, want)
	}
	if evidence.APISpecs[0].Parsed {
		t.Fatal("api_specs[0].Parsed = true, want false for javascript scaffold evidence")
	}
	if got, want := evidence.APISpecs[0].Format, "javascript"; got != want {
		t.Fatalf("api_specs[0].Format = %q, want %q", got, want)
	}
}

func TestLoadServiceQueryEvidencePropagatesReaderErrors(t *testing.T) {
	t.Parallel()

	reader := &stubServiceEvidenceReader{
		listErr: errors.New("boom"),
	}

	_, err := loadServiceQueryEvidence(context.Background(), reader, "repo-sample-service-api", "sample-service-api")
	if err == nil {
		t.Fatal("loadServiceQueryEvidence() error = nil, want non-nil")
	}
}

type stubServiceEvidenceReader struct {
	files       []FileContent
	fileContent map[string]string
	listErr     error
	readErr     error
}

func (s *stubServiceEvidenceReader) ListRepoFiles(context.Context, string, int) ([]FileContent, error) {
	if s.listErr != nil {
		return nil, s.listErr
	}
	return append([]FileContent(nil), s.files...), nil
}

func (s *stubServiceEvidenceReader) GetFileContent(_ context.Context, repoID, relativePath string) (*FileContent, error) {
	if s.readErr != nil {
		return nil, s.readErr
	}
	content, ok := s.fileContent[relativePath]
	if !ok {
		return nil, nil
	}
	return &FileContent{
		RepoID:       repoID,
		RelativePath: relativePath,
		Content:      content,
	}, nil
}

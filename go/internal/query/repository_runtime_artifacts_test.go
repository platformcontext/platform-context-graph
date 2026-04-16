package query

import "testing"

func TestBuildRepositoryRuntimeArtifactsSurfacesDockerComposeRuntimeSignals(t *testing.T) {
	t.Parallel()

	files := []FileContent{
		{
			RelativePath: "docker-compose.yaml",
			ArtifactType: "docker_compose",
			Content: `services:
  api:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
    ports:
      - "8080:8080"
      - "8443:8443"
    environment:
      LOG_LEVEL: info
      PORT: "8080"
    volumes:
      - ./data:/var/lib/app
  worker:
    ports:
      - "9000:9000"
`,
		},
		{
			RelativePath: "README.md",
			ArtifactType: "markdown",
			Content:      "# ignored",
		},
	}

	got := buildRepositoryRuntimeArtifacts(files)
	if got == nil {
		t.Fatal("buildRepositoryRuntimeArtifacts() = nil, want deployment artifacts")
	}

	artifacts, ok := got["deployment_artifacts"].([]map[string]any)
	if !ok {
		t.Fatalf("deployment_artifacts type = %T, want []map[string]any", got["deployment_artifacts"])
	}
	if len(artifacts) != 2 {
		t.Fatalf("len(deployment_artifacts) = %d, want 2", len(artifacts))
	}

	api := artifacts[0]
	if got, want := api["relative_path"], "docker-compose.yaml"; got != want {
		t.Fatalf("api.relative_path = %#v, want %#v", got, want)
	}
	if got, want := api["artifact_type"], "docker_compose"; got != want {
		t.Fatalf("api.artifact_type = %#v, want %#v", got, want)
	}
	if got, want := api["service_name"], "api"; got != want {
		t.Fatalf("api.service_name = %#v, want %#v", got, want)
	}
	if got, want := api["signals"], []string{"healthcheck", "ports", "environment", "volumes"}; !stringSliceEqual(got, want) {
		t.Fatalf("api.signals = %#v, want %#v", got, want)
	}
	if got, want := api["ports"], []string{"8080:8080", "8443:8443"}; !stringSliceEqual(got, want) {
		t.Fatalf("api.ports = %#v, want %#v", got, want)
	}
	if got, want := api["environment"], []string{"LOG_LEVEL", "PORT"}; !stringSliceEqual(got, want) {
		t.Fatalf("api.environment = %#v, want %#v", got, want)
	}
	if got, want := api["volumes"], []string{"./data:/var/lib/app"}; !stringSliceEqual(got, want) {
		t.Fatalf("api.volumes = %#v, want %#v", got, want)
	}

	worker := artifacts[1]
	if got, want := worker["service_name"], "worker"; got != want {
		t.Fatalf("worker.service_name = %#v, want %#v", got, want)
	}
	if got, want := worker["signals"], []string{"ports"}; !stringSliceEqual(got, want) {
		t.Fatalf("worker.signals = %#v, want %#v", got, want)
	}
	if got, want := worker["ports"], []string{"9000:9000"}; !stringSliceEqual(got, want) {
		t.Fatalf("worker.ports = %#v, want %#v", got, want)
	}
	if _, ok := worker["environment"]; ok {
		t.Fatalf("worker.environment present, want omitted")
	}
	if _, ok := worker["volumes"]; ok {
		t.Fatalf("worker.volumes present, want omitted")
	}
}

func TestBuildRepositoryRuntimeArtifactsIgnoresNonComposeFiles(t *testing.T) {
	t.Parallel()

	got := buildRepositoryRuntimeArtifacts([]FileContent{
		{
			RelativePath: "Dockerfile",
			ArtifactType: "dockerfile",
			Content:      "FROM scratch",
		},
		{
			RelativePath: "service.yaml",
			ArtifactType: "yaml",
			Content: `kind: ConfigMap
metadata:
  name: demo
`,
		},
	})

	if got != nil {
		t.Fatalf("buildRepositoryRuntimeArtifacts() = %#v, want nil", got)
	}
}

func TestBuildRepositoryRuntimeArtifactsSurfacesDockerComposeBuildContext(t *testing.T) {
	t.Parallel()

	got := buildRepositoryRuntimeArtifacts([]FileContent{
		{
			RelativePath: "docker-compose.yaml",
			ArtifactType: "docker_compose",
			Content: `services:
  api:
    build: ../payments-service
`,
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryRuntimeArtifacts() = nil, want deployment artifacts")
	}

	artifacts, ok := got["deployment_artifacts"].([]map[string]any)
	if !ok {
		t.Fatalf("deployment_artifacts type = %T, want []map[string]any", got["deployment_artifacts"])
	}
	if len(artifacts) != 1 {
		t.Fatalf("len(deployment_artifacts) = %d, want 1", len(artifacts))
	}

	api := artifacts[0]
	if got, want := api["service_name"], "api"; got != want {
		t.Fatalf("api.service_name = %#v, want %#v", got, want)
	}
	if got, want := api["build_context"], "../payments-service"; got != want {
		t.Fatalf("api.build_context = %#v, want %#v", got, want)
	}
	if got, want := api["signals"], []string{"build"}; !stringSliceEqual(got, want) {
		t.Fatalf("api.signals = %#v, want %#v", got, want)
	}
}

func stringSliceEqual(got any, want []string) bool {
	typed, ok := got.([]string)
	if !ok {
		return false
	}
	if len(typed) != len(want) {
		return false
	}
	for i := range want {
		if typed[i] != want[i] {
			return false
		}
	}
	return true
}

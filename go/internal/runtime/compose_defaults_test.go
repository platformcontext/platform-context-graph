package runtime

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

type composeDocument struct {
	Services map[string]composeService `yaml:"services"`
}

type composeService struct {
	Image       string         `yaml:"image"`
	Environment map[string]any `yaml:"environment"`
}

func TestDefaultComposeUsesNornicDBBackend(t *testing.T) {
	t.Parallel()

	doc := readComposeDocument(t, "docker-compose.yaml")
	if _, ok := doc.Services["nornicdb"]; !ok {
		t.Fatal("docker-compose.yaml missing nornicdb service")
	}
	if _, ok := doc.Services["neo4j"]; ok {
		t.Fatal("docker-compose.yaml includes neo4j service; default compose should use NornicDB")
	}

	for _, serviceName := range graphRuntimeServices() {
		service := requireComposeService(t, doc, serviceName)
		assertComposeEnv(t, service, "PCG_GRAPH_BACKEND", "nornicdb")
		assertComposeEnv(t, service, "DEFAULT_DATABASE", "nornic")
		assertComposeEnv(t, service, "NEO4J_URI", "bolt://nornicdb:7687")
	}
}

func TestNeo4jComposeUsesNeo4jBackend(t *testing.T) {
	t.Parallel()

	doc := readComposeDocument(t, "docker-compose.neo4j.yml")
	if _, ok := doc.Services["neo4j"]; !ok {
		t.Fatal("docker-compose.neo4j.yml missing neo4j service")
	}
	if _, ok := doc.Services["nornicdb"]; ok {
		t.Fatal("docker-compose.neo4j.yml includes nornicdb service")
	}

	for _, serviceName := range graphRuntimeServices() {
		service := requireComposeService(t, doc, serviceName)
		assertComposeEnv(t, service, "PCG_GRAPH_BACKEND", "neo4j")
		assertComposeEnv(t, service, "DEFAULT_DATABASE", "neo4j")
		assertComposeEnv(t, service, "NEO4J_URI", "bolt://neo4j:7687")
	}
}

func graphRuntimeServices() []string {
	return []string{
		"db-migrate",
		"bootstrap-index",
		"platform-context-graph",
		"mcp-server",
		"ingester",
		"resolution-engine",
	}
}

func readComposeDocument(t *testing.T, name string) composeDocument {
	t.Helper()

	raw, err := os.ReadFile(filepath.Join("..", "..", "..", name))
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}

	var doc composeDocument
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("parse %s: %v", name, err)
	}
	return doc
}

func requireComposeService(t *testing.T, doc composeDocument, name string) composeService {
	t.Helper()

	service, ok := doc.Services[name]
	if !ok {
		t.Fatalf("compose service %q missing", name)
	}
	return service
}

func assertComposeEnv(t *testing.T, service composeService, key, want string) {
	t.Helper()

	got, ok := service.Environment[key]
	if !ok {
		t.Fatalf("compose env %s missing", key)
	}
	if got != want {
		t.Fatalf("compose env %s = %#v, want %q", key, got, want)
	}
}

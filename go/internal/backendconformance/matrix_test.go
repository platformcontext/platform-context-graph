package backendconformance

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestBackendConformanceMatrixMatchesCapabilityMatrixBackends(t *testing.T) {
	t.Parallel()

	matrix := loadRepositoryBackendMatrix(t)
	if err := matrix.Validate(); err != nil {
		t.Fatalf("backend conformance matrix invalid: %v", err)
	}

	wantBackends := loadCapabilityMatrixBackends(t)
	if diff := matrix.DiffBackendIDs(wantBackends); diff != "" {
		t.Fatalf("backend conformance matrix backends differ from capability matrix: %s", diff)
	}
}

func TestBackendConformanceMatrixDefinesRequiredCapabilityClasses(t *testing.T) {
	t.Parallel()

	matrix := loadRepositoryBackendMatrix(t)
	if err := matrix.Validate(); err != nil {
		t.Fatalf("backend conformance matrix invalid: %v", err)
	}

	for _, backend := range matrix.Backends {
		for _, capability := range RequiredCapabilityClasses() {
			entry, ok := backend.Capabilities[capability]
			if !ok {
				t.Fatalf("backend %q missing capability class %q", backend.ID, capability)
			}
			if entry.Status == "" {
				t.Fatalf("backend %q capability %q has empty status", backend.ID, capability)
			}
			if entry.Notes == "" {
				t.Fatalf("backend %q capability %q needs notes", backend.ID, capability)
			}
		}
	}
}

func TestBackendConformanceMatrixKeepsNornicDBAsDefault(t *testing.T) {
	t.Parallel()

	matrix := loadRepositoryBackendMatrix(t)
	defaultBackend, err := matrix.DefaultBackend()
	if err != nil {
		t.Fatalf("DefaultBackend() error = %v", err)
	}
	if defaultBackend.ID != BackendNornicDB {
		t.Fatalf("default backend = %q, want %q", defaultBackend.ID, BackendNornicDB)
	}
}

func loadRepositoryBackendMatrix(t *testing.T) Matrix {
	t.Helper()

	raw, err := os.ReadFile(repositoryPath(t, "specs", "backend-conformance.v1.yaml"))
	if err != nil {
		t.Fatalf("read backend conformance matrix: %v", err)
	}
	matrix, err := ParseMatrix(raw)
	if err != nil {
		t.Fatalf("parse backend conformance matrix: %v", err)
	}
	return matrix
}

func loadCapabilityMatrixBackends(t *testing.T) []BackendID {
	t.Helper()

	raw, err := os.ReadFile(repositoryPath(t, "specs", "capability-matrix.v1.yaml"))
	if err != nil {
		t.Fatalf("read capability matrix: %v", err)
	}
	backends, err := ParseCapabilityMatrixBackendIDs(raw)
	if err != nil {
		t.Fatalf("parse capability matrix backends: %v", err)
	}
	return backends
}

func repositoryPath(t *testing.T, parts ...string) string {
	t.Helper()

	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", ".."))
	return filepath.Join(append([]string{root}, parts...)...)
}

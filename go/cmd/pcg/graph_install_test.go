package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/spf13/cobra"
)

func TestInstallNornicDBCopiesVerifiedBinary(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test uses a Unix executable script")
	}

	homeDir := t.TempDir()
	t.Setenv("PCG_HOME", homeDir)
	source := writeFakeNornicDBBinary(t, "NornicDB v1.0.42\n")
	wantSHA := fileSHA256Hex(t, source)

	result, err := installNornicDB(installNornicDBOptions{
		From:   source,
		SHA256: wantSHA,
	})
	if err != nil {
		t.Fatalf("installNornicDB() error = %v, want nil", err)
	}
	if result.Version != "v1.0.42" {
		t.Fatalf("Version = %q, want %q", result.Version, "v1.0.42")
	}
	if result.SHA256 != wantSHA {
		t.Fatalf("SHA256 = %q, want %q", result.SHA256, wantSHA)
	}
	wantBinary := filepath.Join(homeDir, "bin", "nornicdb-headless")
	if result.BinaryPath != wantBinary {
		t.Fatalf("BinaryPath = %q, want %q", result.BinaryPath, wantBinary)
	}
	info, err := os.Stat(wantBinary)
	if err != nil {
		t.Fatalf("os.Stat(installed binary) error = %v, want nil", err)
	}
	if info.Mode().Perm() != 0o755 {
		t.Fatalf("installed binary mode = %v, want 0755", info.Mode().Perm())
	}

	manifestPath := filepath.Join(homeDir, "graph-backends", "nornicdb", "manifest.json")
	content, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatalf("os.ReadFile(manifest) error = %v, want nil", err)
	}
	var manifest nornicDBInstallManifest
	if err := json.Unmarshal(content, &manifest); err != nil {
		t.Fatalf("json.Unmarshal(manifest) error = %v, want nil", err)
	}
	if manifest.Version != "v1.0.42" || manifest.SHA256 != wantSHA || manifest.BinaryPath != wantBinary {
		t.Fatalf("manifest = %+v, want installed version/checksum/path", manifest)
	}
}

func TestInstallNornicDBRejectsChecksumMismatch(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test uses a Unix executable script")
	}

	t.Setenv("PCG_HOME", t.TempDir())
	source := writeFakeNornicDBBinary(t, "NornicDB v1.0.42\n")

	_, err := installNornicDB(installNornicDBOptions{
		From:   source,
		SHA256: strings.Repeat("0", 64),
	})
	if err == nil {
		t.Fatal("installNornicDB() error = nil, want checksum error")
	}
	if !strings.Contains(err.Error(), "sha256 mismatch") {
		t.Fatalf("installNornicDB() error = %q, want sha256 mismatch", err.Error())
	}
}

func TestInstallNornicDBRequiresLocalSourcePath(t *testing.T) {
	t.Setenv("PCG_HOME", t.TempDir())

	_, err := installNornicDB(installNornicDBOptions{})
	if err == nil {
		t.Fatal("installNornicDB() error = nil, want missing source error")
	}
	if !strings.Contains(err.Error(), "requires --from <path>") {
		t.Fatalf("installNornicDB() error = %q, want --from guidance", err.Error())
	}
}

func TestResolveNornicDBBinaryPrefersManagedInstall(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test uses a Unix executable script")
	}

	originalLookPath := localGraphLookPath
	t.Cleanup(func() {
		localGraphLookPath = originalLookPath
	})

	homeDir := t.TempDir()
	t.Setenv("PCG_HOME", homeDir)
	t.Setenv("PCG_NORNICDB_BINARY", "")
	managedPath := filepath.Join(homeDir, "bin", "nornicdb-headless")
	writeFakeNornicDBBinaryAt(t, managedPath, "NornicDB v1.0.43\n")
	localGraphLookPath = func(file string) (string, error) {
		t.Fatalf("localGraphLookPath(%q) called; managed install should win", file)
		return "", nil
	}

	got, err := resolveNornicDBBinary()
	if err != nil {
		t.Fatalf("resolveNornicDBBinary() error = %v, want nil", err)
	}
	if got != managedPath {
		t.Fatalf("resolveNornicDBBinary() = %q, want %q", got, managedPath)
	}
}

func TestRunInstallNornicDBPrintsJSON(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test uses a Unix executable script")
	}

	t.Setenv("PCG_HOME", t.TempDir())
	source := writeFakeNornicDBBinary(t, "NornicDB v1.0.42\n")
	cmd := &cobra.Command{}
	cmd.Flags().String("from", source, "")
	cmd.Flags().String("sha256", "", "")
	cmd.Flags().Bool("force", false, "")

	output := captureStdout(t, func() {
		if err := runInstallNornicDB(cmd, nil); err != nil {
			t.Fatalf("runInstallNornicDB() error = %v, want nil", err)
		}
	})

	var got installNornicDBResult
	if err := json.Unmarshal([]byte(output), &got); err != nil {
		t.Fatalf("json.Unmarshal(output) error = %v, output=%q", err, output)
	}
	if got.Version != "v1.0.42" {
		t.Fatalf("Version = %q, want %q", got.Version, "v1.0.42")
	}
	if !got.Installed {
		t.Fatal("Installed = false for first install, want true")
	}
}

func writeFakeNornicDBBinary(t *testing.T, versionOutput string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "nornicdb-headless")
	writeFakeNornicDBBinaryAt(t, path, versionOutput)
	return path
}

func writeFakeNornicDBBinaryAt(t *testing.T, path, versionOutput string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatalf("os.MkdirAll(%q) error = %v, want nil", filepath.Dir(path), err)
	}
	script := "#!/bin/sh\nif [ \"$1\" = \"version\" ]; then printf '" + versionOutput + "'; exit 0; fi\nexit 0\n"
	if err := os.WriteFile(path, []byte(script), 0o755); err != nil {
		t.Fatalf("os.WriteFile(fake binary) error = %v, want nil", err)
	}
}

func fileSHA256Hex(t *testing.T, path string) string {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("os.ReadFile(%q) error = %v, want nil", path, err)
	}
	sum := sha256.Sum256(content)
	return hex.EncodeToString(sum[:])
}

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSetConfigValuePersistsApiKey(t *testing.T) {
	home := t.TempDir()
	t.Setenv(appHomeEnvVar, home)

	if err := setConfigValue("PCG_API_KEY", "local-compose-token"); err != nil {
		t.Fatalf("setConfigValue() error = %v, want nil", err)
	}

	got := resolveConfigValue("PCG_API_KEY", "")
	if got != "local-compose-token" {
		t.Fatalf("resolveConfigValue() = %q, want %q", got, "local-compose-token")
	}

	envBytes, err := os.ReadFile(filepath.Join(home, envFileName))
	if err != nil {
		t.Fatalf("ReadFile() error = %v, want nil", err)
	}
	if !strings.Contains(string(envBytes), "PCG_API_KEY=local-compose-token") {
		t.Fatalf(".env = %q, want persisted token", string(envBytes))
	}
}

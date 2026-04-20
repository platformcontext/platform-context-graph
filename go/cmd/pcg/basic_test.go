package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/spf13/cobra"
)

func TestRunQueryPostsLanguageQueryRequest(t *testing.T) {
	t.Parallel()

	var gotPath string
	var gotBody map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		if err := json.NewDecoder(r.Body).Decode(&gotBody); err != nil {
			t.Fatalf("json.Decode() error = %v, want nil", err)
		}
		_, _ = w.Write([]byte(`{"results":[]}`))
	}))
	defer server.Close()

	cmd := &cobra.Command{}
	addRemoteFlags(cmd)
	if err := cmd.Flags().Set("service-url", server.URL); err != nil {
		t.Fatalf("Set(service-url) error = %v, want nil", err)
	}

	if err := runQuery(cmd, []string{"Service"}); err != nil {
		t.Fatalf("runQuery() error = %v, want nil", err)
	}
	if got, want := gotPath, "/api/v0/code/language-query"; got != want {
		t.Fatalf("request path = %q, want %q", got, want)
	}
	if got, want := gotBody["query"], "Service"; got != want {
		t.Fatalf("body[query] = %#v, want %#v", got, want)
	}
}

func TestRunDeleteAllReturnsRemovedContractError(t *testing.T) {
	t.Parallel()

	cmd := &cobra.Command{}
	cmd.Flags().Bool("all", false, "")
	if err := cmd.Flags().Set("all", "true"); err != nil {
		t.Fatalf("Set(all) error = %v, want nil", err)
	}

	err := runDelete(cmd, nil)
	if err == nil {
		t.Fatal("runDelete(--all) error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "removed") {
		t.Fatalf("runDelete(--all) error = %q, want removed guidance", err.Error())
	}
}

func TestRunCleanReturnsRemovedContractError(t *testing.T) {
	t.Parallel()

	err := runClean(&cobra.Command{}, nil)
	if err == nil {
		t.Fatal("runClean() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "removed") {
		t.Fatalf("runClean() error = %q, want removed guidance", err.Error())
	}
}

func TestRunUnwatchReturnsRemovedContractError(t *testing.T) {
	t.Parallel()

	err := runUnwatch(&cobra.Command{}, []string{"/tmp/repo"})
	if err == nil {
		t.Fatal("runUnwatch() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "removed") {
		t.Fatalf("runUnwatch() error = %q, want removed guidance", err.Error())
	}
}

func TestRunWatchingReturnsRemovedContractError(t *testing.T) {
	t.Parallel()

	err := runWatching(&cobra.Command{}, nil)
	if err == nil {
		t.Fatal("runWatching() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "removed") {
		t.Fatalf("runWatching() error = %q, want removed guidance", err.Error())
	}
}

func TestRunAddPackageReturnsRemovedContractError(t *testing.T) {
	t.Parallel()

	err := runAddPackage(&cobra.Command{}, []string{"demo", "go"})
	if err == nil {
		t.Fatal("runAddPackage() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "removed") {
		t.Fatalf("runAddPackage() error = %q, want removed guidance", err.Error())
	}
}

package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/spf13/cobra"
)

func TestRunAnalyzeChainPostsCanonicalRequest(t *testing.T) {
	t.Parallel()

	var gotPath string
	var gotBody map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		if err := json.NewDecoder(r.Body).Decode(&gotBody); err != nil {
			t.Fatalf("json.Decode() error = %v, want nil", err)
		}
		_, _ = w.Write([]byte(`{"chains":[]}`))
	}))
	defer server.Close()

	cmd := &cobra.Command{}
	addRemoteFlags(cmd)
	cmd.Flags().Int("depth", 5, "Maximum traversal depth")
	if err := cmd.Flags().Set("service-url", server.URL); err != nil {
		t.Fatalf("Set(service-url) error = %v, want nil", err)
	}
	if err := cmd.Flags().Set("depth", "7"); err != nil {
		t.Fatalf("Set(depth) error = %v, want nil", err)
	}

	if err := runAnalyzeChain(cmd, []string{"wrapper", "helper"}); err != nil {
		t.Fatalf("runAnalyzeChain() error = %v, want nil", err)
	}
	if got, want := gotPath, "/api/v0/code/call-chain"; got != want {
		t.Fatalf("request path = %q, want %q", got, want)
	}
	if got, want := gotBody["start"], "wrapper"; got != want {
		t.Fatalf("body[start] = %#v, want %#v", got, want)
	}
	if got, want := gotBody["end"], "helper"; got != want {
		t.Fatalf("body[end] = %#v, want %#v", got, want)
	}
	if got, want := gotBody["max_depth"], float64(7); got != want {
		t.Fatalf("body[max_depth] = %#v, want %#v", got, want)
	}
}

func TestRunAnalyzeDeadCodePostsExclusions(t *testing.T) {
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
	cmd.Flags().String("repo-id", "", "Optional repository ID")
	cmd.Flags().StringSlice("exclude", nil, "Decorator exclusions")
	cmd.Flags().Bool("fail-on-found", false, "Exit non-zero when results are found")
	if err := cmd.Flags().Set("service-url", server.URL); err != nil {
		t.Fatalf("Set(service-url) error = %v, want nil", err)
	}
	if err := cmd.Flags().Set("repo-id", "repo-1"); err != nil {
		t.Fatalf("Set(repo-id) error = %v, want nil", err)
	}
	if err := cmd.Flags().Set("exclude", "@route,@app.route"); err != nil {
		t.Fatalf("Set(exclude) error = %v, want nil", err)
	}

	if err := runAnalyzeDeadCode(cmd, nil); err != nil {
		t.Fatalf("runAnalyzeDeadCode() error = %v, want nil", err)
	}
	if got, want := gotPath, "/api/v0/code/dead-code"; got != want {
		t.Fatalf("request path = %q, want %q", got, want)
	}
	if got, want := gotBody["repo_id"], "repo-1"; got != want {
		t.Fatalf("body[repo_id] = %#v, want %#v", got, want)
	}
	exclusions, ok := gotBody["exclude_decorated_with"].([]any)
	if !ok {
		t.Fatalf("body[exclude_decorated_with] type = %T, want []any", gotBody["exclude_decorated_with"])
	}
	if got, want := len(exclusions), 2; got != want {
		t.Fatalf("len(body[exclude_decorated_with]) = %d, want %d", got, want)
	}
}

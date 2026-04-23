package main

import (
	"context"
	"strings"
	"testing"
)

func TestWireAPIReturnsResolveAPIKeyErrorBeforeConnectingDatastores(t *testing.T) {
	t.Setenv("PCG_API_KEY", "")
	t.Setenv("PCG_AUTO_GENERATE_API_KEY", "true")
	t.Setenv("PCG_HOME", "/dev/null/pcg")

	_, _, _, err := wireAPI(context.Background(), func(string) string {
		return ""
	}, nil, nil)
	if err == nil {
		t.Fatal("wireAPI() error = nil, want non-nil")
	}
}

func TestWireAPIReturnsInvalidQueryProfileErrorBeforeConnectingDatastores(t *testing.T) {
	_, _, _, err := wireAPI(context.Background(), func(key string) string {
		if key == "PCG_QUERY_PROFILE" {
			return "not-a-real-profile"
		}
		return ""
	}, nil, nil)
	if err == nil {
		t.Fatal("wireAPI() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "load query profile") {
		t.Fatalf("wireAPI() error = %q, want load query profile context", err)
	}
}

func TestOpenQueryGraphRejectsUnsupportedGraphBackend(t *testing.T) {
	t.Parallel()

	_, _, err := openQueryGraph(context.Background(), func(key string) string {
		switch key {
		case "PCG_GRAPH_BACKEND":
			return "nornicdb"
		case "PCG_QUERY_PROFILE":
			return "production"
		default:
			return ""
		}
	}, "production", nil)
	if err == nil {
		t.Fatal("openQueryGraph() error = nil, want non-nil")
	}
	if !strings.Contains(err.Error(), "graph backend") {
		t.Fatalf("openQueryGraph() error = %q, want graph backend context", err)
	}
}

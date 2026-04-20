package main

import (
	"context"
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

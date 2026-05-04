//go:build nolocalllm

package main

import (
	"context"
	"io"
	"testing"
	"time"
)

func TestEmbeddedLocalNornicDBRuntimeStartsHTTPAndBolt(t *testing.T) {
	boltPort, err := reserveLocalGraphPort()
	if err != nil {
		t.Fatalf("reserve bolt port: %v", err)
	}
	httpPort, err := reserveLocalGraphPort()
	if err != nil {
		t.Fatalf("reserve http port: %v", err)
	}

	runtime, err := startEmbeddedNornicDBRuntime(t.TempDir(), localNornicDBBindAddress, boltPort, httpPort, io.Discard)
	if err != nil {
		t.Fatalf("startEmbeddedNornicDBRuntime() error = %v, want nil", err)
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), localGraphShutdownTimeout)
		defer cancel()
		if err := runtime.stop(ctx); err != nil {
			t.Fatalf("stop embedded runtime: %v", err)
		}
	})

	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if graphHTTPHealthy(localNornicDBBindAddress, httpPort, localGraphHealthTimeout) &&
			graphBoltHealthy(localNornicDBBindAddress, boltPort, localGraphHealthTimeout) {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatal("embedded NornicDB runtime did not become healthy")
}

package runtime

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

func TestNewStatusAdminServerServesStatusAndReadyChecks(t *testing.T) {
	t.Parallel()

	reader := &fakeStatusReader{
		snapshot: statuspkg.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
		},
	}

	server, err := NewStatusAdminServer(
		Config{
			ServiceName: "collector-git",
			ListenAddr:  "127.0.0.1:0",
		},
		reader,
	)
	if err != nil {
		t.Fatalf("NewStatusAdminServer() error = %v, want nil", err)
	}
	if err := server.Start(context.Background()); err != nil {
		t.Fatalf("Start() error = %v, want nil", err)
	}
	defer server.Stop(context.Background())

	statusResponse, err := http.Get("http://" + server.Addr() + "/admin/status?format=json")
	if err != nil {
		t.Fatalf("GET /admin/status error = %v, want nil", err)
	}
	defer statusResponse.Body.Close()
	if got, want := statusResponse.StatusCode, http.StatusOK; got != want {
		t.Fatalf("GET /admin/status status = %d, want %d", got, want)
	}

	readyResponse, err := http.Get("http://" + server.Addr() + "/readyz")
	if err != nil {
		t.Fatalf("GET /readyz error = %v, want nil", err)
	}
	defer readyResponse.Body.Close()
	if got, want := readyResponse.StatusCode, http.StatusOK; got != want {
		t.Fatalf("GET /readyz status = %d, want %d", got, want)
	}
}

func TestNewStatusAdminServerServesMetrics(t *testing.T) {
	t.Parallel()

	reader := &fakeStatusReader{
		snapshot: statuspkg.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			Queue: statuspkg.QueueSnapshot{
				Outstanding:          2,
				OldestOutstandingAge: 30 * time.Second,
			},
		},
	}

	server, err := NewStatusAdminServer(
		Config{
			ServiceName: "collector-git",
			ListenAddr:  "127.0.0.1:0",
		},
		reader,
	)
	if err != nil {
		t.Fatalf("NewStatusAdminServer() error = %v, want nil", err)
	}
	if err := server.Start(context.Background()); err != nil {
		t.Fatalf("Start() error = %v, want nil", err)
	}
	defer server.Stop(context.Background())

	response, err := http.Get("http://" + server.Addr() + "/metrics")
	if err != nil {
		t.Fatalf("GET /metrics error = %v, want nil", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatalf("ReadAll() error = %v, want nil", err)
	}

	if got, want := response.StatusCode, http.StatusOK; got != want {
		t.Fatalf("GET /metrics status = %d, want %d", got, want)
	}
	if got := string(body); !strings.Contains(got, `pcg_runtime_queue_outstanding{service_name="collector-git"} 2`) {
		t.Fatalf("GET /metrics body = %q, want queue metric", got)
	}
}

func TestNewStatusAdminServerSurfacesReaderFailureThroughReadyz(t *testing.T) {
	t.Parallel()

	server, err := NewStatusAdminServer(
		Config{
			ServiceName: "collector-git",
			ListenAddr:  "127.0.0.1:0",
		},
		&fakeStatusReader{err: errors.New("postgres unavailable")},
	)
	if err != nil {
		t.Fatalf("NewStatusAdminServer() error = %v, want nil", err)
	}
	if err := server.Start(context.Background()); err != nil {
		t.Fatalf("Start() error = %v, want nil", err)
	}
	defer server.Stop(context.Background())

	response, err := http.Get("http://" + server.Addr() + "/readyz")
	if err != nil {
		t.Fatalf("GET /readyz error = %v, want nil", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatalf("ReadAll() error = %v, want nil", err)
	}

	if got, want := response.StatusCode, http.StatusServiceUnavailable; got != want {
		t.Fatalf("GET /readyz status = %d, want %d", got, want)
	}
	if got := string(body); got == "" {
		t.Fatal("GET /readyz body = empty, want readiness error details")
	}
}

type fakeStatusReader struct {
	snapshot statuspkg.RawSnapshot
	err      error
}

func (r *fakeStatusReader) ReadStatusSnapshot(context.Context, time.Time) (statuspkg.RawSnapshot, error) {
	if r.err != nil {
		return statuspkg.RawSnapshot{}, r.err
	}
	return r.snapshot, nil
}

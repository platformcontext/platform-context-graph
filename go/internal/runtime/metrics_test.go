package runtime

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

func TestNewStatusMetricsHandlerRequiresInputs(t *testing.T) {
	t.Parallel()

	if _, err := NewStatusMetricsHandler("   ", &fakeStatusReader{}); err == nil {
		t.Fatal("NewStatusMetricsHandler() error = nil, want non-nil for blank service")
	}

	if _, err := NewStatusMetricsHandler("collector-git", nil); err == nil {
		t.Fatal("NewStatusMetricsHandler() error = nil, want non-nil for nil reader")
	}
}

func TestStatusMetricsHandlerServesRuntimeMetrics(t *testing.T) {
	t.Parallel()

	handler, err := NewStatusMetricsHandler("collector-git", &fakeStatusReader{
		snapshot: statuspkg.RawSnapshot{
			AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC),
			ScopeActivity: statuspkg.ScopeActivitySnapshot{
				Active:  7,
				Changed: 3,
			},
			Queue: statuspkg.QueueSnapshot{
				Total:                4,
				Outstanding:          2,
				Pending:              1,
				InFlight:             1,
				Retrying:             1,
				Succeeded:            2,
				Failed:               0,
				OldestOutstandingAge: 45 * time.Second,
				OverdueClaims:        0,
			},
			GenerationCounts: []statuspkg.NamedCount{{Name: "completed", Count: 3}},
			StageCounts:      []statuspkg.StageStatusCount{{Stage: "projector", Status: "running", Count: 1}},
			DomainBacklogs:   []statuspkg.DomainBacklog{{Domain: "repository", Outstanding: 2, OldestAge: 30 * time.Second}},
		},
	})
	if err != nil {
		t.Fatalf("NewStatusMetricsHandler() error = %v, want nil", err)
	}

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	handler.ServeHTTP(recorder, request)

	if got, want := recorder.Code, http.StatusOK; got != want {
		t.Fatalf("GET /metrics status = %d, want %d", got, want)
	}
	body := recorder.Body.String()
	for _, want := range []string{
		`pcg_runtime_info{service_name="collector-git",service_namespace="platform-context-graph"} 1`,
		`pcg_runtime_scope_active{service_name="collector-git"} 7`,
		`pcg_runtime_scope_changed{service_name="collector-git"} 3`,
		`pcg_runtime_queue_outstanding{service_name="collector-git"} 2`,
		`pcg_runtime_queue_oldest_outstanding_age_seconds{service_name="collector-git"} 45`,
		`pcg_runtime_health_state{service_name="collector-git",state="progressing"} 1`,
		`pcg_runtime_stage_items{service_name="collector-git",stage="projector",status="running"} 1`,
		`pcg_runtime_domain_outstanding{domain="repository",service_name="collector-git"} 2`,
	} {
		if !strings.Contains(body, want) {
			t.Fatalf("GET /metrics body missing %q\nbody:\n%s", want, body)
		}
	}
}

func TestStatusMetricsHandlerSupportsHeadWithoutBody(t *testing.T) {
	t.Parallel()

	handler, err := NewStatusMetricsHandler("collector-git", &fakeStatusReader{
		snapshot: statuspkg.RawSnapshot{AsOf: time.Date(2026, 4, 12, 16, 0, 0, 0, time.UTC)},
	})
	if err != nil {
		t.Fatalf("NewStatusMetricsHandler() error = %v, want nil", err)
	}

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodHead, "/metrics", nil)
	handler.ServeHTTP(recorder, request)

	if got, want := recorder.Code, http.StatusOK; got != want {
		t.Fatalf("HEAD /metrics status = %d, want %d", got, want)
	}
	if got := recorder.Body.String(); got != "" {
		t.Fatalf("HEAD /metrics body = %q, want empty", got)
	}
}

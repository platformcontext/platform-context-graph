package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestWireAPIReturnsResolveAPIKeyErrorBeforeConnectingDatastores(t *testing.T) {
	t.Setenv("PCG_API_KEY", "")
	t.Setenv("PCG_AUTO_GENERATE_API_KEY", "true")
	t.Setenv("PCG_HOME", "/dev/null/pcg")

	_, _, err := wireAPI(context.Background(), func(key string) string {
		return ""
	}, nil, nil)
	if err == nil {
		t.Fatal("wireAPI() error = nil, want non-nil")
	}
}

func TestNewRouter_MountsAdminRoutes(t *testing.T) {
	t.Parallel()

	router, err := newRouter(nil, nil, nil)
	if err != nil {
		t.Fatalf("newRouter() error = %v, want nil", err)
	}

	mux := http.NewServeMux()
	router.Mount(mux)

	tests := []struct {
		name       string
		method     string
		path       string
		wantStatus int
	}{
		{
			name:       "reindex is mounted",
			method:     http.MethodPost,
			path:       "/api/v0/admin/reindex",
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "work item query is mounted",
			method:     http.MethodPost,
			path:       "/api/v0/admin/work-items/query",
			wantStatus: http.StatusServiceUnavailable,
		},
		{
			name:       "tuning report is mounted",
			method:     http.MethodGet,
			path:       "/api/v0/admin/shared-projection/tuning-report",
			wantStatus: http.StatusOK,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			req := httptest.NewRequest(tt.method, tt.path, nil)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if got, want := rec.Code, tt.wantStatus; got != want {
				t.Fatalf("%s %s status = %d, want %d; body: %s", tt.method, tt.path, got, want, rec.Body.String())
			}
		})
	}
}

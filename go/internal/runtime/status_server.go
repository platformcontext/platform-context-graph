package runtime

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

const defaultStatusReadinessTimeout = 3 * time.Second

// StatusAdminOption configures optional behavior on the status admin server.
type StatusAdminOption func(*statusAdminOptions)

type statusAdminOptions struct {
	recoveryHandler   *RecoveryHandler
	prometheusHandler http.Handler
}

// WithRecoveryHandler attaches a recovery handler to the admin mux, mounting
// /admin/replay and /admin/refinalize routes alongside the standard probes.
func WithRecoveryHandler(rh *RecoveryHandler) StatusAdminOption {
	return func(o *statusAdminOptions) {
		o.recoveryHandler = rh
	}
}

// WithPrometheusHandler attaches an OTEL Prometheus exporter handler that is
// served alongside the existing status-based metrics on /metrics.
func WithPrometheusHandler(h http.Handler) StatusAdminOption {
	return func(o *statusAdminOptions) {
		o.prometheusHandler = h
	}
}

// NewStatusAdminServer builds the shared admin HTTP server for a long-running
// runtime using the storage-backed status reader seam.
func NewStatusAdminServer(cfg Config, reader statuspkg.Reader, opts ...StatusAdminOption) (*HTTPServer, error) {
	var options statusAdminOptions
	for _, opt := range opts {
		opt(&options)
	}

	statusHandler, err := statuspkg.NewHTTPHandler(reader, statuspkg.HTTPHandlerOptions{})
	if err != nil {
		return nil, err
	}
	metricsHandler, err := NewStatusMetricsHandler(cfg.ServiceName, reader)
	if err != nil {
		return nil, err
	}

	// Wrap metrics handler with OTEL Prometheus exporter if provided
	if options.prometheusHandler != nil {
		metricsHandler = compositeMetricsHandler{
			statusHandler:     metricsHandler,
			prometheusHandler: options.prometheusHandler,
		}
	}

	adminMux, err := NewAdminMux(AdminMuxConfig{
		ServiceName:     cfg.ServiceName,
		Ready:           statusReadinessCheck(reader),
		StatusHandler:   statusHandler,
		MetricsHandler:  metricsHandler,
		RecoveryHandler: options.recoveryHandler,
	})
	if err != nil {
		return nil, err
	}

	return NewHTTPServer(HTTPServerConfig{
		Addr:    cfg.ListenAddr,
		Handler: adminMux,
	})
}

func statusReadinessCheck(reader statuspkg.Reader) AdminCheck {
	return func() error {
		ctx, cancel := context.WithTimeout(context.Background(), defaultStatusReadinessTimeout)
		defer cancel()

		_, err := reader.ReadStatusSnapshot(ctx, time.Now().UTC())
		if err != nil {
			return fmt.Errorf("read status snapshot: %w", err)
		}
		return nil
	}
}

// compositeMetricsHandler combines the hand-rolled status metrics with the
// OTEL Prometheus exporter output.
type compositeMetricsHandler struct {
	statusHandler     http.Handler // existing hand-rolled pcg_runtime_* metrics
	prometheusHandler http.Handler // OTEL prometheus exporter
}

func (h compositeMetricsHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Capture OTEL prometheus metrics into buffer
	promRec := httptest.NewRecorder()
	h.prometheusHandler.ServeHTTP(promRec, r)

	// Capture status metrics into buffer
	statusRec := httptest.NewRecorder()
	h.statusHandler.ServeHTTP(statusRec, r)

	// Write combined output: OTEL metrics first, then status metrics
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(promRec.Body.Bytes())
	_, _ = w.Write([]byte("\n"))
	_, _ = w.Write(statusRec.Body.Bytes())
}

package runtime

import (
	"context"
	"fmt"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

const defaultStatusReadinessTimeout = 3 * time.Second

// StatusAdminOption configures optional behavior on the status admin server.
type StatusAdminOption func(*statusAdminOptions)

type statusAdminOptions struct {
	recoveryHandler *RecoveryHandler
}

// WithRecoveryHandler attaches a recovery handler to the admin mux, mounting
// /admin/replay and /admin/refinalize routes alongside the standard probes.
func WithRecoveryHandler(rh *RecoveryHandler) StatusAdminOption {
	return func(o *statusAdminOptions) {
		o.recoveryHandler = rh
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

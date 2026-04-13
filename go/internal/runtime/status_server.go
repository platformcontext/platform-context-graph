package runtime

import (
	"context"
	"fmt"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

const defaultStatusReadinessTimeout = 3 * time.Second

// NewStatusAdminServer builds the shared admin HTTP server for a long-running
// runtime using the storage-backed status reader seam.
func NewStatusAdminServer(cfg Config, reader statuspkg.Reader) (*HTTPServer, error) {
	statusHandler, err := statuspkg.NewHTTPHandler(reader, statuspkg.HTTPHandlerOptions{})
	if err != nil {
		return nil, err
	}
	metricsHandler, err := NewStatusMetricsHandler(cfg.ServiceName, reader)
	if err != nil {
		return nil, err
	}

	adminMux, err := NewAdminMux(AdminMuxConfig{
		ServiceName:    cfg.ServiceName,
		Ready:          statusReadinessCheck(reader),
		StatusHandler:  statusHandler,
		MetricsHandler: metricsHandler,
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

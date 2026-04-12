package runtime

import (
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

// NewStatusAdminServer builds the shared admin HTTP server for a long-running
// runtime using the storage-backed status reader seam.
func NewStatusAdminServer(cfg Config, reader statuspkg.Reader) (*HTTPServer, error) {
	statusHandler, err := statuspkg.NewHTTPHandler(reader, statuspkg.HTTPHandlerOptions{})
	if err != nil {
		return nil, err
	}

	adminMux, err := NewAdminMux(AdminMuxConfig{
		ServiceName:   cfg.ServiceName,
		StatusHandler: statusHandler,
	})
	if err != nil {
		return nil, err
	}

	return NewHTTPServer(HTTPServerConfig{
		Addr:    cfg.ListenAddr,
		Handler: adminMux,
	})
}

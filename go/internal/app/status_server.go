package app

import (
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
)

// MountStatusServer composes the shared mounted runtime admin surface into an
// existing hosted application.
func MountStatusServer(app Application, reader statuspkg.Reader, opts ...runtimecfg.StatusAdminOption) (Application, error) {
	adminServer, err := runtimecfg.NewStatusAdminServer(app.Config, reader, opts...)
	if err != nil {
		return Application{}, err
	}

	app.Lifecycle = ComposeLifecycles(app.Lifecycle, adminServer)
	return app, nil
}

// NewHostedWithStatusServer builds one hosted application with the shared
// mounted runtime admin surface already attached.
func NewHostedWithStatusServer(serviceName string, runner Runner, reader statuspkg.Reader, opts ...runtimecfg.StatusAdminOption) (Application, error) {
	app, err := NewHosted(serviceName, runner)
	if err != nil {
		return Application{}, err
	}

	return MountStatusServer(app, reader, opts...)
}

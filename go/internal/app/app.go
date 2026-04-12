package app

import (
	"context"

	"github.com/platformcontext/platform-context-graph/go/internal/runtime"
)

// Application wires the shared runtime config and lifecycle for a command.
type Application struct {
	Config        runtime.Config
	Observability runtime.Observability
	Lifecycle     runtime.Lifecycle
}

// New constructs a bootable application for the named service.
func New(serviceName string) (Application, error) {
	cfg, err := runtime.LoadConfig(serviceName)
	if err != nil {
		return Application{}, err
	}

	lifecycle, err := runtime.NewLifecycle(cfg)
	if err != nil {
		return Application{}, err
	}

	return Application{
		Config:        cfg,
		Observability: runtime.NewObservability(),
		Lifecycle:     lifecycle,
	}, nil
}

// Run starts the service and waits for shutdown.
func (a Application) Run(ctx context.Context) error {
	if err := a.Lifecycle.Start(ctx); err != nil {
		return err
	}
	defer a.Lifecycle.Stop(context.Background())

	return a.Lifecycle.Run(ctx)
}

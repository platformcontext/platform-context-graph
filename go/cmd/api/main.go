package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	bootstrap, err := telemetry.NewBootstrap("platform-context-graph-api")
	if err != nil {
		fallback := slog.New(slog.NewJSONHandler(os.Stderr, nil))
		fallback.Error("api bootstrap failed", "event_name", "runtime.startup.failed", "error", err)
		os.Exit(1)
	}
	logger := newLogger(bootstrap, os.Stderr)
	providers, err := telemetry.NewProviders(ctx, bootstrap)
	if err != nil {
		logger.Error("api telemetry providers failed", telemetry.EventAttr("runtime.startup.failed"), "error", err)
		os.Exit(1)
	}
	defer func() {
		if err := providers.Shutdown(context.Background()); err != nil {
			logger.Error("telemetry shutdown failed", telemetry.EventAttr("runtime.shutdown.failed"), "error", err)
		}
	}()

	mux, cleanup, err := wireAPI(ctx, os.Getenv, logger)
	if err != nil {
		logger.Error("wire api failed", telemetry.EventAttr("runtime.startup.failed"), "error", err)
		os.Exit(1)
	}
	defer cleanup()

	addr := os.Getenv("PCG_API_ADDR")
	if addr == "" {
		addr = ":8080"
	}

	handler := otelhttp.NewHandler(mux, "pcg-api",
		otelhttp.WithMessageEvents(otelhttp.ReadEvents, otelhttp.WriteEvents),
	)

	srv := &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = srv.Shutdown(shutdownCtx)
	}()

	logger.Info("pcg-api listening on address", telemetry.EventAttr("runtime.server.listening"), "address", addr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Error("api listen failed", telemetry.EventAttr("runtime.server.failed"), "error", err, "address", addr)
		os.Exit(1)
	}
	logger.Info("pcg-api shutdown complete", telemetry.EventAttr("runtime.server.stopped"))
}

func newLogger(bootstrap telemetry.Bootstrap, writer io.Writer) *slog.Logger {
	return telemetry.NewLoggerWithWriter(bootstrap, "api", "api", writer)
}

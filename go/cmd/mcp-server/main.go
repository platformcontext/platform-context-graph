package main

import (
	"context"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/platformcontext/platform-context-graph/go/internal/mcp"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	bootstrap, err := telemetry.NewBootstrap("mcp-server")
	if err != nil {
		fallback := slog.New(slog.NewJSONHandler(os.Stderr, nil))
		fallback.Error("mcp bootstrap failed", "event_name", "runtime.startup.failed", "error", err)
		os.Exit(1)
	}
	logger := newLogger(bootstrap, os.Stderr)
	providers, err := telemetry.NewProviders(ctx, bootstrap)
	if err != nil {
		logger.Error("mcp telemetry providers failed", telemetry.EventAttr("runtime.startup.failed"), "error", err)
		os.Exit(1)
	}
	defer func() {
		if err := providers.Shutdown(context.Background()); err != nil {
			logger.Error("telemetry shutdown failed", telemetry.EventAttr("runtime.shutdown.failed"), "error", err)
		}
	}()

	transport := strings.ToLower(strings.TrimSpace(os.Getenv("PCG_MCP_TRANSPORT")))
	if transport == "" {
		transport = "http"
	}

	queryMux, adminMux, cleanup, err := wireAPI(ctx, os.Getenv, logger, providers.PrometheusHandler)
	if err != nil {
		logger.Error("wire api failed", telemetry.EventAttr("runtime.startup.failed"), "error", err)
		os.Exit(1)
	}
	defer cleanup()

	// Note: MCP server's internal httpMux handles auth for its own endpoints (/sse, /mcp/message, /health).
	// The query API routes mounted under /api/ are protected by the query mux itself.
	server := mcp.NewServer(queryMux, logger)

	switch transport {
	case "stdio":
		if err := server.Run(ctx); err != nil {
			logger.Error("mcp server exited", "transport", "stdio", "error", err)
			os.Exit(1)
		}
	case "http":
		addr := os.Getenv("PCG_MCP_ADDR")
		if addr == "" {
			addr = ":8080"
		}
		if err := server.RunHTTP(ctx, addr, adminMux); err != nil {
			logger.Error("mcp server exited", "transport", "http", "error", err)
			os.Exit(1)
		}
	default:
		logger.Error("unknown transport", "PCG_MCP_TRANSPORT", transport)
		os.Exit(1)
	}
}

func newLogger(bootstrap telemetry.Bootstrap, writer io.Writer) *slog.Logger {
	return telemetry.NewLoggerWithWriter(bootstrap, "mcp-server", "mcp-server", writer)
}

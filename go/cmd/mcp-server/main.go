package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/platformcontext/platform-context-graph/go/internal/mcp"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	logger := slog.New(slog.NewJSONHandler(os.Stderr, nil))

	transport := strings.ToLower(strings.TrimSpace(os.Getenv("PCG_MCP_TRANSPORT")))
	if transport == "" {
		transport = "http"
	}

	mux, cleanup, err := wireAPI(ctx, os.Getenv)
	if err != nil {
		logger.Error("wire api failed", "error", err)
		os.Exit(1)
	}
	defer cleanup()

	server := mcp.NewServer(mux, logger)

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
		if err := server.RunHTTP(ctx, addr); err != nil {
			logger.Error("mcp server exited", "transport", "http", "error", err)
			os.Exit(1)
		}
	default:
		logger.Error("unknown transport", "PCG_MCP_TRANSPORT", transport)
		os.Exit(1)
	}
}

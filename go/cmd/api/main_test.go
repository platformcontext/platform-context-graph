package main

import (
	"bytes"
	"encoding/json"
	"log/slog"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewLoggerOutputsStructuredJSON(t *testing.T) {
	t.Parallel()

	bootstrap, err := telemetry.NewBootstrap("platform-context-graph-api")
	require.NoError(t, err)

	var buf bytes.Buffer
	logger := newLogger(bootstrap, &buf)

	logger.Info("api starting", slog.String("listen_addr", ":8080"))

	var logEntry map[string]any
	require.NoError(t, json.Unmarshal(buf.Bytes(), &logEntry))

	assert.Equal(t, "platform-context-graph-api", logEntry["service_name"])
	assert.Equal(t, "platform-context-graph", logEntry["service_namespace"])
	assert.Equal(t, "api", logEntry["component"])
	assert.Equal(t, "api", logEntry["runtime_role"])
	assert.Equal(t, "api starting", logEntry["message"])
	assert.Equal(t, "INFO", logEntry["severity_text"])
	assert.Equal(t, ":8080", logEntry["listen_addr"])
}

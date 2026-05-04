//go:build nolocalllm

package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"

	nornicbolt "github.com/orneryd/nornicdb/pkg/bolt"
	nornicbuildinfo "github.com/orneryd/nornicdb/pkg/buildinfo"
	nornicconfig "github.com/orneryd/nornicdb/pkg/config"
	"github.com/orneryd/nornicdb/pkg/nornicdb"
	nornicserver "github.com/orneryd/nornicdb/pkg/server"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

// embeddedLocalNornicDBAvailable reports that this PCG binary was built with
// the NornicDB library-mode runtime linked in.
func embeddedLocalNornicDBAvailable() bool {
	return true
}

// startEmbeddedLocalNornicDB starts NornicDB in the local owner process while
// exposing the same HTTP and Bolt ports that the process runtime records.
func startEmbeddedLocalNornicDB(ctx context.Context, layout pcglocal.Layout) (*managedLocalGraph, error) {
	boltPort, err := reserveLocalGraphPort()
	if err != nil {
		return nil, err
	}
	httpPort, err := reserveLocalGraphPort()
	if err != nil {
		return nil, err
	}

	dataDir := filepath.Join(layout.GraphDir, "nornicdb")
	logPath := filepath.Join(layout.LogsDir, "graph-nornicdb.log")
	if err := os.MkdirAll(dataDir, 0o700); err != nil {
		return nil, fmt.Errorf("create graph data directory: %w", err)
	}
	if err := os.MkdirAll(layout.LogsDir, 0o700); err != nil {
		return nil, fmt.Errorf("create graph logs directory: %w", err)
	}
	credentials, err := loadOrCreateLocalGraphCredentials(filepath.Join(dataDir, "pcg-credentials.json"))
	if err != nil {
		return nil, err
	}

	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return nil, fmt.Errorf("open graph log file: %w", err)
	}
	embedded, err := startEmbeddedNornicDBRuntime(dataDir, localNornicDBBindAddress, boltPort, httpPort, logFile)
	if err != nil {
		_ = logFile.Close()
		return nil, err
	}

	graph := &managedLocalGraph{
		Backend:  query.GraphBackendNornicDB,
		Version:  nornicbuildinfo.DisplayVersion(),
		Address:  localNornicDBBindAddress,
		BoltPort: boltPort,
		HTTPPort: httpPort,
		DataDir:  dataDir,
		LogPath:  logPath,
		Username: credentials.Username,
		Password: credentials.Password,
		PID:      os.Getpid(),
		logFile:  logFile,
		shutdown: embedded.stop,
	}
	if err := waitForManagedLocalGraph(ctx, graph, localGraphStartupTimeout); err != nil {
		_ = stopManagedLocalGraph(graph, localGraphShutdownTimeout)
		return nil, err
	}
	return graph, nil
}

type embeddedNornicDBRuntime struct {
	db         *nornicdb.DB
	httpServer *nornicserver.Server
	boltServer *nornicbolt.Server
}

// startEmbeddedNornicDBRuntime composes NornicDB's public DB, HTTP server, and
// Bolt server APIs into PCG's local graph lifecycle. The runtime disables
// optional local AI and MCP surfaces so `pcg graph start` only owns graph
// storage for PCG.
func startEmbeddedNornicDBRuntime(dataDir string, address string, boltPort int, httpPort int, logs io.Writer) (*embeddedNornicDBRuntime, error) {
	if logs == nil {
		logs = io.Discard
	}
	dbConfig := nornicdb.DefaultConfig()
	dbConfig.Database.DataDir = dataDir
	dbConfig.Database.DefaultDatabase = localNornicDBDefaultDatabase
	dbConfig.Memory.EmbeddingEnabled = false
	dbConfig.Features.HeimdallEnabled = false
	dbConfig.Features.QdrantGRPCEnabled = false

	db, err := nornicdb.Open(dataDir, dbConfig)
	if err != nil {
		return nil, fmt.Errorf("open embedded nornicdb: %w", err)
	}
	runtime := &embeddedNornicDBRuntime{db: db}
	defer func() {
		if err != nil {
			_ = runtime.stop(context.Background())
		}
	}()

	serverConfig := nornicserver.DefaultConfig()
	serverConfig.Address = address
	serverConfig.Port = httpPort
	serverConfig.MCPEnabled = false
	serverConfig.EmbeddingEnabled = false
	serverConfig.Headless = true
	serverConfig.Features = &nornicconfig.FeatureFlagsConfig{
		HeimdallEnabled:     false,
		QdrantGRPCEnabled:   false,
		SearchRerankEnabled: false,
	}
	httpServer, err := nornicserver.New(db, nil, serverConfig)
	if err != nil {
		return nil, fmt.Errorf("create embedded nornicdb http server: %w", err)
	}
	runtime.httpServer = httpServer
	if err = httpServer.Start(); err != nil {
		return nil, fmt.Errorf("start embedded nornicdb http server: %w", err)
	}

	boltConfig := nornicbolt.DefaultConfig()
	boltConfig.Host = address
	boltConfig.Port = boltPort
	boltConfig.RequireAuth = false
	boltServer := nornicbolt.NewWithDatabaseManager(boltConfig, nil, httpServer.GetDatabaseManager())
	runtime.boltServer = boltServer
	go func() {
		if serveErr := boltServer.ListenAndServe(); serveErr != nil {
			_, _ = fmt.Fprintf(logs, "embedded nornicdb bolt server error: %v\n", serveErr)
		}
	}()

	return runtime, nil
}

// stop shuts down the embedded servers before closing storage so pending Bolt
// or HTTP handlers stop accepting work before the underlying graph files close.
func (r *embeddedNornicDBRuntime) stop(ctx context.Context) error {
	if r == nil {
		return nil
	}
	var err error
	if r.boltServer != nil {
		err = errors.Join(err, r.boltServer.Close())
	}
	if r.httpServer != nil {
		err = errors.Join(err, r.httpServer.Stop(ctx))
	}
	if r.db != nil {
		r.db.StopEmbedQueue()
		err = errors.Join(err, r.db.Close())
	}
	return err
}

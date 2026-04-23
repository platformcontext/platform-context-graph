package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

const (
	localGraphStartupTimeout  = 45 * time.Second
	localGraphHealthTimeout   = 1 * time.Second
	localGraphShutdownTimeout = 10 * time.Second

	localNornicDBBindAddress     = "127.0.0.1"
	localNornicDBAdminUsername   = "admin"
	localNornicDBAdminPassword   = "pcg-local-graph"
	localNornicDBDefaultDatabase = "nornic"
)

var (
	localGraphLookPath    = exec.LookPath
	localGraphHTTPHealthy = graphHTTPHealthy
	localGraphBoltHealthy = graphBoltHealthy
)

type managedLocalGraph struct {
	Backend    query.GraphBackend
	Version    string
	BinaryPath string
	Address    string
	BoltPort   int
	HTTPPort   int
	DataDir    string
	LogPath    string
	PID        int
	Cmd        *exec.Cmd
	logFile    io.Closer
}

func startManagedLocalGraph(ctx context.Context, layout pcglocal.Layout, runtimeConfig localHostRuntimeConfig) (*managedLocalGraph, error) {
	switch runtimeConfig.GraphBackend {
	case query.GraphBackendNornicDB:
		return startManagedLocalNornicDB(ctx, layout)
	default:
		return nil, fmt.Errorf("graph backend %q is not supported by local_authoritative host", runtimeConfig.GraphBackend)
	}
}

func startManagedLocalNornicDB(ctx context.Context, layout pcglocal.Layout) (*managedLocalGraph, error) {
	binaryPath, err := resolveNornicDBBinary()
	if err != nil {
		return nil, err
	}
	version, err := readLocalGraphVersion(binaryPath)
	if err != nil {
		return nil, err
	}

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

	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return nil, fmt.Errorf("open graph log file: %w", err)
	}

	args := []string{
		"serve",
		"--headless",
		"--mcp-enabled=false",
		"--address=" + localNornicDBBindAddress,
		fmt.Sprintf("--bolt-port=%d", boltPort),
		fmt.Sprintf("--http-port=%d", httpPort),
		"--data-dir=" + dataDir,
		"--admin-password=" + localNornicDBAdminPassword,
	}
	cmd := exec.Command(binaryPath, args...)
	cmd.Args = append([]string{binaryPath}, args...)
	cmd.Env = mergeEnvironment(pcgEnviron(), map[string]string{
		"NORNICDB_ADDRESS":          localNornicDBBindAddress,
		"NORNICDB_BOLT_PORT":        fmt.Sprintf("%d", boltPort),
		"NORNICDB_HTTP_PORT":        fmt.Sprintf("%d", httpPort),
		"NORNICDB_DATA_DIR":         dataDir,
		"NORNICDB_MCP_ENABLED":      "false",
		"NORNICDB_HEADLESS":         "true",
		"NORNICDB_DEFAULT_DATABASE": localNornicDBDefaultDatabase,
	})
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	if err := cmd.Start(); err != nil {
		_ = logFile.Close()
		return nil, fmt.Errorf("start nornicdb: %w", err)
	}

	graph := &managedLocalGraph{
		Backend:    query.GraphBackendNornicDB,
		Version:    version,
		BinaryPath: binaryPath,
		Address:    localNornicDBBindAddress,
		BoltPort:   boltPort,
		HTTPPort:   httpPort,
		DataDir:    dataDir,
		LogPath:    logPath,
		PID:        cmd.Process.Pid,
		Cmd:        cmd,
		logFile:    logFile,
	}
	if err := waitForManagedLocalGraph(ctx, graph, localGraphStartupTimeout); err != nil {
		_ = stopManagedLocalGraph(graph, localGraphShutdownTimeout)
		return nil, err
	}
	return graph, nil
}

func resolveNornicDBBinary() (string, error) {
	if raw := strings.TrimSpace(os.Getenv("PCG_NORNICDB_BINARY")); raw != "" {
		return raw, nil
	}
	for _, name := range []string{"nornicdb-headless", "nornicdb"} {
		binaryPath, err := localGraphLookPath(name)
		if err == nil {
			return binaryPath, nil
		}
	}
	return "", fmt.Errorf("resolve nornicdb binary: set PCG_NORNICDB_BINARY or place nornicdb-headless in PATH")
}

func readLocalGraphVersion(binaryPath string) (string, error) {
	output, err := exec.Command(binaryPath, "version").Output()
	if err != nil {
		return "", fmt.Errorf("read nornicdb version: %w", err)
	}
	version := strings.TrimSpace(string(output))
	version = strings.TrimPrefix(version, "NornicDB ")
	if version == "" {
		return "", fmt.Errorf("read nornicdb version: empty output")
	}
	return version, nil
}

func reserveLocalGraphPort() (int, error) {
	listener, err := net.Listen("tcp", net.JoinHostPort(localNornicDBBindAddress, "0"))
	if err != nil {
		return 0, fmt.Errorf("reserve local graph port: %w", err)
	}
	defer func() {
		_ = listener.Close()
	}()

	addr, ok := listener.Addr().(*net.TCPAddr)
	if !ok || addr.Port <= 0 {
		return 0, fmt.Errorf("reserve local graph port: invalid tcp address %T", listener.Addr())
	}
	return addr.Port, nil
}

func waitForManagedLocalGraph(ctx context.Context, graph *managedLocalGraph, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for {
		if graphHealthyFromOwnerRecord(pcglocal.OwnerRecord{
			GraphPID:      graph.PID,
			GraphAddress:  graph.Address,
			GraphBoltPort: graph.BoltPort,
			GraphHTTPPort: graph.HTTPPort,
		}) {
			return nil
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("wait for graph backend readiness timed out after %s; see %s", timeout, graph.LogPath)
		}
		if graph.Cmd != nil && graph.Cmd.ProcessState != nil && graph.Cmd.ProcessState.Exited() {
			return fmt.Errorf("graph backend exited before becoming ready; see %s", graph.LogPath)
		}
		time.Sleep(200 * time.Millisecond)
	}
}

func stopManagedLocalGraph(graph *managedLocalGraph, timeout time.Duration) error {
	if graph == nil {
		return nil
	}
	defer func() {
		if graph.logFile != nil {
			_ = graph.logFile.Close()
		}
	}()

	if graph.Cmd == nil || graph.Cmd.Process == nil {
		return nil
	}
	if graph.Cmd.ProcessState != nil && graph.Cmd.ProcessState.Exited() {
		return nil
	}
	if err := graph.Cmd.Process.Signal(syscall.SIGTERM); err != nil && !errors.Is(err, os.ErrProcessDone) {
		_ = graph.Cmd.Process.Kill()
		return fmt.Errorf("signal graph backend: %w", err)
	}

	done := make(chan error, 1)
	go func() {
		done <- graph.Cmd.Wait()
	}()

	select {
	case err := <-done:
		if err == nil {
			return nil
		}
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			return nil
		}
		return err
	case <-time.After(timeout):
		if err := graph.Cmd.Process.Kill(); err != nil && !errors.Is(err, os.ErrProcessDone) {
			return fmt.Errorf("kill graph backend: %w", err)
		}
		<-done
		return nil
	}
}

func stopRecordedLocalGraph(record pcglocal.OwnerRecord) error {
	graph := managedGraphFromRecord(record)
	if graph == nil {
		return nil
	}
	process, err := os.FindProcess(graph.PID)
	if err != nil {
		return fmt.Errorf("find graph backend process: %w", err)
	}
	if err := process.Signal(syscall.SIGTERM); err != nil && !errors.Is(err, os.ErrProcessDone) {
		return fmt.Errorf("signal graph backend: %w", err)
	}
	deadline := time.Now().Add(localGraphShutdownTimeout)
	for time.Now().Before(deadline) {
		if !graphHealthyFromOwnerRecord(record) {
			return nil
		}
		time.Sleep(200 * time.Millisecond)
	}
	if err := process.Kill(); err != nil && !errors.Is(err, os.ErrProcessDone) {
		return fmt.Errorf("kill graph backend: %w", err)
	}
	return nil
}

func managedGraphFromRecord(record pcglocal.OwnerRecord) *managedLocalGraph {
	if record.GraphBackend == "" {
		return nil
	}
	return &managedLocalGraph{
		Backend:    query.GraphBackend(record.GraphBackend),
		Version:    record.GraphVersion,
		Address:    record.GraphAddress,
		BoltPort:   record.GraphBoltPort,
		HTTPPort:   record.GraphHTTPPort,
		DataDir:    record.GraphDataDir,
		PID:        record.GraphPID,
		BinaryPath: "",
	}
}

func graphEnvOverrides(graph *managedLocalGraph) map[string]string {
	if graph == nil || graph.Backend != query.GraphBackendNornicDB {
		return nil
	}
	boltURI := fmt.Sprintf("bolt://%s:%d", graph.Address, graph.BoltPort)
	return map[string]string{
		"PCG_NEO4J_URI":      boltURI,
		"PCG_NEO4J_USERNAME": localNornicDBAdminUsername,
		"PCG_NEO4J_PASSWORD": localNornicDBAdminPassword,
		"PCG_NEO4J_DATABASE": localNornicDBDefaultDatabase,
		"NEO4J_URI":          boltURI,
		"NEO4J_USERNAME":     localNornicDBAdminUsername,
		"NEO4J_PASSWORD":     localNornicDBAdminPassword,
		"NEO4J_DATABASE":     localNornicDBDefaultDatabase,
		"DEFAULT_DATABASE":   localNornicDBDefaultDatabase,
	}
}

func graphAddress(graph *managedLocalGraph) string {
	if graph == nil {
		return ""
	}
	return graph.Address
}

func graphPID(graph *managedLocalGraph) int {
	if graph == nil {
		return 0
	}
	return graph.PID
}

func graphBoltPort(graph *managedLocalGraph) int {
	if graph == nil {
		return 0
	}
	return graph.BoltPort
}

func graphHTTPPort(graph *managedLocalGraph) int {
	if graph == nil {
		return 0
	}
	return graph.HTTPPort
}

func graphDataDir(graph *managedLocalGraph) string {
	if graph == nil {
		return ""
	}
	return graph.DataDir
}

func graphVersion(graph *managedLocalGraph) string {
	if graph == nil {
		return ""
	}
	return graph.Version
}

func graphHealthyFromOwnerRecord(record pcglocal.OwnerRecord) bool {
	if record.GraphPID <= 0 {
		return false
	}
	address := strings.TrimSpace(record.GraphAddress)
	if address == "" {
		address = localNornicDBBindAddress
	}
	if record.GraphBoltPort <= 0 || record.GraphHTTPPort <= 0 {
		return false
	}
	return localHostProcessAlive(record.GraphPID) &&
		localGraphHTTPHealthy(address, record.GraphHTTPPort, localGraphHealthTimeout) &&
		localGraphBoltHealthy(address, record.GraphBoltPort, localGraphHealthTimeout)
}

func graphHTTPHealthy(address string, port int, timeout time.Duration) bool {
	client := &http.Client{Timeout: timeout}
	resp, err := client.Get(fmt.Sprintf("http://%s:%d/health", address, port))
	if err != nil {
		return false
	}
	defer func() {
		_ = resp.Body.Close()
	}()
	return resp.StatusCode == http.StatusOK
}

func graphBoltHealthy(address string, port int, timeout time.Duration) bool {
	conn, err := net.DialTimeout("tcp", net.JoinHostPort(address, fmt.Sprintf("%d", port)), timeout)
	if err != nil {
		return false
	}
	_ = conn.Close()
	return true
}

package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
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
	localNornicDBDefaultDatabase = "nornic"
)

var (
	localGraphLookPath         = exec.LookPath
	localGraphReadVersion      = readLocalGraphVersion
	localGraphGeneratePassword = generateLocalGraphPassword
	localGraphHTTPHealthy      = graphHTTPHealthy
	localGraphBoltHealthy      = graphBoltHealthy
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
	Username   string
	Password   string
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
	credentials, err := loadOrCreateLocalGraphCredentials(filepath.Join(dataDir, "pcg-credentials.json"))
	if err != nil {
		return nil, err
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
		"NORNICDB_AUTH":             credentials.Username + "/" + credentials.Password,
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
		Username:   credentials.Username,
		Password:   credentials.Password,
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
		if _, err := localGraphReadVersion(raw); err != nil {
			return "", fmt.Errorf("verify nornicdb binary %q: %w", raw, err)
		}
		return raw, nil
	}
	if binaryPath, err := managedNornicDBBinaryIfPresent(); err == nil {
		return binaryPath, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}
	var verifyErrs []error
	for _, name := range []string{"nornicdb-headless", "nornicdb"} {
		binaryPath, err := localGraphLookPath(name)
		if err == nil {
			if _, err := localGraphReadVersion(binaryPath); err != nil {
				verifyErrs = append(verifyErrs, fmt.Errorf("%s at %q: %w", name, binaryPath, err))
				continue
			}
			return binaryPath, nil
		}
	}
	if len(verifyErrs) > 0 {
		return "", fmt.Errorf("resolve nornicdb binary: discovered candidate binaries but none passed version verification: %v", verifyErrs)
	}
	return "", fmt.Errorf("resolve nornicdb binary: set PCG_NORNICDB_BINARY or place nornicdb-headless in PATH")
}

func readLocalGraphVersion(binaryPath string) (string, error) {
	output, err := exec.Command(binaryPath, "version").Output()
	if err != nil {
		return "", fmt.Errorf("read nornicdb version: %w", err)
	}
	return parseNornicDBVersionOutput(string(output))
}

func parseNornicDBVersionOutput(output string) (string, error) {
	version := strings.TrimSpace(output)
	if version == "" {
		return "", fmt.Errorf("empty output")
	}
	const prefix = "NornicDB "
	if !strings.HasPrefix(version, prefix) {
		return "", fmt.Errorf("unexpected output %q", version)
	}
	version = strings.TrimSpace(strings.TrimPrefix(version, prefix))
	if version == "" {
		return "", fmt.Errorf("missing version in output %q", output)
	}
	return version, nil
}

func generateLocalGraphPassword() (string, error) {
	var raw [32]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", fmt.Errorf("generate local graph password: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(raw[:]), nil
}

type localGraphCredentials struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

func loadOrCreateLocalGraphCredentials(path string) (localGraphCredentials, error) {
	content, err := os.ReadFile(path)
	if err == nil {
		var credentials localGraphCredentials
		if err := json.Unmarshal(content, &credentials); err != nil {
			return localGraphCredentials{}, fmt.Errorf("decode local graph credentials: %w", err)
		}
		if strings.TrimSpace(credentials.Username) == "" || strings.TrimSpace(credentials.Password) == "" {
			return localGraphCredentials{}, fmt.Errorf("decode local graph credentials: username and password are required")
		}
		return credentials, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return localGraphCredentials{}, fmt.Errorf("read local graph credentials: %w", err)
	}

	password, err := localGraphGeneratePassword()
	if err != nil {
		return localGraphCredentials{}, err
	}
	credentials := localGraphCredentials{
		Username: localNornicDBAdminUsername,
		Password: password,
	}
	if err := writeLocalGraphCredentials(path, credentials); err != nil {
		return localGraphCredentials{}, err
	}
	return credentials, nil
}

func writeLocalGraphCredentials(path string, credentials localGraphCredentials) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("create local graph credentials directory: %w", err)
	}
	content, err := json.MarshalIndent(credentials, "", "  ")
	if err != nil {
		return fmt.Errorf("encode local graph credentials: %w", err)
	}
	content = append(content, '\n')

	tempFile, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+".*.tmp")
	if err != nil {
		return fmt.Errorf("create local graph credentials temp file: %w", err)
	}
	tempPath := tempFile.Name()
	defer func() {
		_ = os.Remove(tempPath)
	}()

	if _, err := tempFile.Write(content); err != nil {
		_ = tempFile.Close()
		return fmt.Errorf("write local graph credentials temp file: %w", err)
	}
	if err := tempFile.Chmod(0o600); err != nil {
		_ = tempFile.Close()
		return fmt.Errorf("chmod local graph credentials temp file: %w", err)
	}
	if err := tempFile.Sync(); err != nil {
		_ = tempFile.Close()
		return fmt.Errorf("sync local graph credentials temp file: %w", err)
	}
	if err := tempFile.Close(); err != nil {
		return fmt.Errorf("close local graph credentials temp file: %w", err)
	}
	if err := os.Rename(tempPath, path); err != nil {
		return fmt.Errorf("replace local graph credentials: %w", err)
	}
	return nil
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
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if graphHealthyFromOwnerRecord(pcglocal.OwnerRecord{
			GraphPID:      graph.PID,
			GraphAddress:  graph.Address,
			GraphBoltPort: graph.BoltPort,
			GraphHTTPPort: graph.HTTPPort,
		}) {
			return nil
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
		Username:   record.GraphUsername,
		Password:   record.GraphPassword,
		BinaryPath: "",
	}
}

func graphEnvOverrides(graph *managedLocalGraph) map[string]string {
	if graph == nil || graph.Backend != query.GraphBackendNornicDB {
		return nil
	}
	boltURI := fmt.Sprintf("bolt://%s:%d", graph.Address, graph.BoltPort)
	username := graph.Username
	if username == "" {
		username = localNornicDBAdminUsername
	}
	// Keep the PCG-prefixed variables as canonical and NEO4J_* as legacy
	// compatibility for code paths that have not yet moved to PCG_* names.
	return map[string]string{
		"PCG_NEO4J_URI":      boltURI,
		"PCG_NEO4J_USERNAME": username,
		"PCG_NEO4J_PASSWORD": graph.Password,
		"PCG_NEO4J_DATABASE": localNornicDBDefaultDatabase,
		"NEO4J_URI":          boltURI,
		"NEO4J_USERNAME":     username,
		"NEO4J_PASSWORD":     graph.Password,
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

func graphUsername(graph *managedLocalGraph) string {
	if graph == nil {
		return ""
	}
	return graph.Username
}

func graphPassword(graph *managedLocalGraph) string {
	if graph == nil {
		return ""
	}
	return graph.Password
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

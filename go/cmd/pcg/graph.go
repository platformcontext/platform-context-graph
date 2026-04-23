package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
)

var (
	graphGetwd       = os.Getwd
	graphBuildLayout = func(workspaceRoot string) (pcglocal.Layout, error) {
		return pcglocal.BuildLayout(os.Getenv, os.UserHomeDir, runtime.GOOS, workspaceRoot)
	}
	graphReadOwnerRecord   = pcglocal.ReadOwnerRecord
	graphResolveBinary     = resolveNornicDBBinary
	graphReadVersion       = readLocalGraphVersion
	graphProcessAlive      = pcglocal.ProcessAlive
	graphStopGraphHealthy  = graphHealthyFromOwnerRecord
	graphStopRecordedGraph = stopRecordedLocalGraph
	graphSignalProcess     = signalProcess
	graphStopPollInterval  = 200 * time.Millisecond
	graphStopTimeout       = localGraphShutdownTimeout
	graphInstallNornicDB   = installNornicDB
)

type graphStatusOutput struct {
	WorkspaceRoot   string `json:"workspace_root"`
	WorkspaceID     string `json:"workspace_id"`
	OwnerPresent    bool   `json:"owner_present"`
	OwnerPID        int    `json:"owner_pid,omitempty"`
	OwnerStarted    string `json:"owner_started_at,omitempty"`
	Profile         string `json:"profile,omitempty"`
	GraphBackend    string `json:"graph_backend,omitempty"`
	GraphInstalled  bool   `json:"graph_installed"`
	GraphBinaryPath string `json:"graph_binary_path,omitempty"`
	GraphRunning    bool   `json:"graph_running"`
	GraphPID        int    `json:"graph_pid,omitempty"`
	GraphAddress    string `json:"graph_address,omitempty"`
	GraphBoltPort   int    `json:"graph_bolt_port,omitempty"`
	GraphHTTPPort   int    `json:"graph_http_port,omitempty"`
	GraphDataDir    string `json:"graph_data_dir,omitempty"`
	GraphLogPath    string `json:"graph_log_path,omitempty"`
	GraphVersion    string `json:"graph_version,omitempty"`
}

func init() {
	graphCmd := &cobra.Command{
		Use:   "graph",
		Short: "Local graph backend operations",
	}
	rootCmd.AddCommand(graphCmd)

	installCmd := &cobra.Command{
		Use:   "install",
		Short: "Install local graph backend tooling",
	}
	rootCmd.AddCommand(installCmd)

	installNornicDBCmd := &cobra.Command{
		Use:   "nornicdb",
		Short: "Install the local NornicDB binary",
		Long: strings.TrimSpace(`
Install a verified local NornicDB executable into PCG's managed home.

Current support includes a pinned bare install where PCG already knows a
host-specific artifact, plus explicit-source installs:

  pcg install nornicdb

  pcg install nornicdb --from /absolute/path/to/nornicdb-headless
  pcg install nornicdb --from /absolute/path/to/nornicdb-headless-darwin-arm64.tar.gz
  pcg install nornicdb --from /absolute/path/to/NornicDB-1.0.42-hotfix-arm64-lite.pkg
  pcg install nornicdb --from https://example.com/releases/nornicdb-headless-darwin-arm64.tar.gz --sha256 <expected-sha256>
  pcg install nornicdb --from https://example.com/releases/NornicDB-1.0.42-hotfix-arm64-lite.pkg --sha256 <expected-sha256>

Pinned bare install is only available for platforms recorded in PCG's embedded
release manifest. Signature verification is still future work.
`),
		RunE: runInstallNornicDB,
	}
	installNornicDBCmd.Flags().String("from", "", "Install from a local NornicDB binary, local archive/package, or release URL")
	installNornicDBCmd.Flags().String("sha256", "", "Expected SHA-256 checksum for the --from artifact")
	installNornicDBCmd.Flags().Bool("force", false, "Replace an existing managed NornicDB binary")
	installCmd.AddCommand(installNornicDBCmd)

	statusCmd := &cobra.Command{
		Use:   "status",
		Short: "Show local graph backend status for the current workspace",
		RunE:  runGraphStatus,
	}
	statusCmd.Flags().String("workspace-root", "", "Explicit workspace root for local graph status")
	graphCmd.AddCommand(statusCmd)

	graphStartCmd := &cobra.Command{
		Use:   "start",
		Short: "Start the local graph backend sidecar",
		Long: strings.TrimSpace(`
Start the local_authoritative workspace owner in the foreground.

The graph backend sidecar is owned by the local host, so this command execs
the same supervisor used by:

  PCG_QUERY_PROFILE=local_authoritative pcg watch .

Use Ctrl-C to stop it from the same terminal, or run "pcg graph stop" from
another terminal for the same workspace.
`),
		RunE: runGraphStart,
	}
	graphStartCmd.Flags().String("workspace-root", "", "Explicit workspace root for local graph start")
	graphCmd.AddCommand(graphStartCmd)
	graphStopCmd := &cobra.Command{
		Use:   "stop",
		Short: "Stop the local graph backend sidecar",
		RunE:  runGraphStop,
	}
	graphStopCmd.Flags().String("workspace-root", "", "Explicit workspace root for local graph stop")
	graphCmd.AddCommand(graphStopCmd)
	graphLogsCmd := &cobra.Command{
		Use:   "logs",
		Short: "Show local graph backend logs",
		RunE:  runGraphLogs,
	}
	graphLogsCmd.Flags().String("workspace-root", "", "Explicit workspace root for local graph logs")
	graphCmd.AddCommand(graphLogsCmd)
	graphUpgradeCmd := &cobra.Command{
		Use:   "upgrade",
		Short: "Upgrade the local graph backend sidecar",
		Long: strings.TrimSpace(`
Replace the managed local NornicDB binary from a verified source artifact.

The graph backend must be stopped first. This command accepts the same binary,
archive/package, and URL sources as pcg install nornicdb:

  pcg graph upgrade --from /absolute/path/to/nornicdb-headless
  pcg graph upgrade --from https://example.com/releases/nornicdb-headless-darwin-arm64.tar.gz --sha256 <expected-sha256>
  pcg graph upgrade --from https://example.com/releases/NornicDB-1.0.42-hotfix-arm64-lite.pkg --sha256 <expected-sha256>
`),
		RunE: runGraphUpgrade,
	}
	graphUpgradeCmd.Flags().String("workspace-root", "", "Explicit workspace root for local graph upgrade")
	graphUpgradeCmd.Flags().String("from", "", "Upgrade from an existing local NornicDB binary")
	graphUpgradeCmd.Flags().String("sha256", "", "Expected SHA-256 checksum for --from")
	graphCmd.AddCommand(graphUpgradeCmd)
}

func runGraphStatus(cmd *cobra.Command, args []string) error {
	layout, err := graphLayoutFromCommand(cmd)
	if err != nil {
		return err
	}

	status, err := graphStatusForLayout(layout)
	if err != nil {
		return err
	}
	printJSON(status)
	return nil
}

func runGraphLogs(cmd *cobra.Command, args []string) error {
	if len(args) > 0 {
		return fmt.Errorf("pcg graph logs accepts flags only, got %d argument(s)", len(args))
	}
	layout, err := graphLayoutFromCommand(cmd)
	if err != nil {
		return err
	}
	return graphLogsForLayout(layout)
}

func runGraphStart(cmd *cobra.Command, args []string) error {
	if len(args) > 0 {
		return fmt.Errorf("pcg graph start accepts flags only, got %d argument(s)", len(args))
	}
	layout, err := graphLayoutFromCommand(cmd)
	if err != nil {
		return err
	}
	binary, err := pcgExecutable()
	if err != nil {
		return fmt.Errorf("resolve pcg executable: %w", err)
	}
	env := mergeEnvironment(pcgEnviron(), map[string]string{
		"PCG_QUERY_PROFILE": string(query.ProfileLocalAuthoritative),
		"PCG_GRAPH_BACKEND": string(query.GraphBackendNornicDB),
	})
	fmt.Fprintf(os.Stderr, "Starting local_authoritative workspace owner for %s...\n", layout.WorkspaceRoot)
	return pcgExec(binary, []string{cleanExecutableArg0(binary), "local-host", "watch", layout.WorkspaceRoot}, env)
}

func runGraphStop(cmd *cobra.Command, args []string) error {
	if len(args) > 0 {
		return fmt.Errorf("pcg graph stop accepts flags only, got %d argument(s)", len(args))
	}
	layout, err := graphLayoutFromCommand(cmd)
	if err != nil {
		return err
	}
	return graphStopForLayout(layout)
}

func runGraphUpgrade(cmd *cobra.Command, args []string) error {
	if len(args) > 0 {
		return fmt.Errorf("pcg graph upgrade accepts flags only, got %d argument(s)", len(args))
	}
	layout, err := graphLayoutFromCommand(cmd)
	if err != nil {
		return err
	}
	from, err := cmd.Flags().GetString("from")
	if err != nil {
		return err
	}
	checksum, err := cmd.Flags().GetString("sha256")
	if err != nil {
		return err
	}
	result, err := graphUpgradeForLayout(layout, installNornicDBOptions{
		From:   from,
		SHA256: checksum,
		Force:  true,
	})
	if err != nil {
		return err
	}
	printJSON(result)
	return nil
}

func graphLayoutFromCommand(cmd *cobra.Command) (pcglocal.Layout, error) {
	startPath, err := graphGetwd()
	if err != nil {
		return pcglocal.Layout{}, fmt.Errorf("resolve current working directory: %w", err)
	}
	explicitRoot, err := cmd.Flags().GetString("workspace-root")
	if err != nil {
		return pcglocal.Layout{}, err
	}
	workspaceRoot, err := pcglocal.ResolveWorkspaceRoot(startPath, explicitRoot)
	if err != nil {
		return pcglocal.Layout{}, err
	}
	layout, err := graphBuildLayout(workspaceRoot)
	if err != nil {
		return pcglocal.Layout{}, err
	}
	return layout, nil
}

func graphStatusForLayout(layout pcglocal.Layout) (graphStatusOutput, error) {
	status := graphStatusOutput{
		WorkspaceRoot: layout.WorkspaceRoot,
		WorkspaceID:   layout.WorkspaceID,
		GraphLogPath:  filepath.Join(layout.LogsDir, "graph-nornicdb.log"),
	}
	if binaryPath, err := graphResolveBinary(); err == nil {
		status.GraphInstalled = true
		status.GraphBinaryPath = binaryPath
		if version, versionErr := graphReadVersion(binaryPath); versionErr == nil {
			status.GraphVersion = version
		}
	}

	record, err := graphReadOwnerRecord(layout.OwnerRecordPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return status, nil
		}
		return graphStatusOutput{}, err
	}

	status.OwnerPresent = true
	status.OwnerPID = record.PID
	status.OwnerStarted = record.StartedAt
	status.GraphPID = record.GraphPID
	status.GraphAddress = record.GraphAddress
	status.GraphBoltPort = record.GraphBoltPort
	status.GraphHTTPPort = record.GraphHTTPPort
	status.GraphDataDir = record.GraphDataDir
	if record.GraphVersion != "" {
		status.GraphVersion = record.GraphVersion
	}

	runtimeConfig, err := runtimeConfigFromOwnerRecord(record)
	if err != nil {
		return graphStatusOutput{}, err
	}
	status.Profile = string(runtimeConfig.Profile)
	status.GraphBackend = string(runtimeConfig.GraphBackend)

	if runtimeConfig.Profile == query.ProfileLocalAuthoritative {
		status.GraphRunning = graphHealthyFromOwnerRecord(record)
	}

	return status, nil
}

func graphLogsForLayout(layout pcglocal.Layout) error {
	logPath := filepath.Join(layout.LogsDir, "graph-nornicdb.log")
	file, err := os.Open(logPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("graph log does not exist at %q; start local_authoritative with pcg watch first", logPath)
		}
		return fmt.Errorf("open graph log %q: %w", logPath, err)
	}
	defer func() {
		_ = file.Close()
	}()
	if _, err := io.Copy(os.Stdout, file); err != nil {
		return fmt.Errorf("print graph log %q: %w", logPath, err)
	}
	return nil
}

func graphStopForLayout(layout pcglocal.Layout) error {
	record, err := graphReadOwnerRecord(layout.OwnerRecordPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return fmt.Errorf("no local graph owner record for workspace %q", layout.WorkspaceRoot)
		}
		return err
	}

	runtimeConfig, err := runtimeConfigFromOwnerRecord(record)
	if err != nil {
		return err
	}
	if runtimeConfig.Profile != query.ProfileLocalAuthoritative || record.GraphPID <= 0 {
		return fmt.Errorf("workspace %q has no local_authoritative graph backend to stop", layout.WorkspaceRoot)
	}

	if graphProcessAlive(record.PID) {
		if err := graphSignalProcess(record.PID, syscall.SIGTERM); err != nil && !errors.Is(err, os.ErrProcessDone) {
			return fmt.Errorf("signal workspace owner pid %d to stop graph backend: %w", record.PID, err)
		}
		return waitForGraphStop(record, graphStopTimeout)
	}

	if !graphStopGraphHealthy(record) {
		return nil
	}
	if err := graphStopRecordedGraph(record); err != nil {
		return err
	}
	return waitForGraphStop(record, graphStopTimeout)
}

func graphUpgradeForLayout(layout pcglocal.Layout, opts installNornicDBOptions) (installNornicDBResult, error) {
	record, err := graphReadOwnerRecord(layout.OwnerRecordPath)
	if err == nil && (graphProcessAlive(record.PID) || graphStopGraphHealthy(record)) {
		return installNornicDBResult{}, fmt.Errorf("workspace graph backend is running; run pcg graph stop before upgrade")
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return installNornicDBResult{}, err
	}
	opts.Force = true
	return graphInstallNornicDB(opts)
}

func waitForGraphStop(record pcglocal.OwnerRecord, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if !graphStopGraphHealthy(record) {
			return nil
		}
		time.Sleep(graphStopPollInterval)
	}
	return fmt.Errorf("graph backend pid %d did not stop within %s", record.GraphPID, timeout)
}

func signalProcess(pid int, signal os.Signal) error {
	process, err := os.FindProcess(pid)
	if err != nil {
		return fmt.Errorf("find process %d: %w", pid, err)
	}
	return process.Signal(signal)
}

func graphLifecycleNotWired(command string) error {
	printError(fmt.Sprintf("%q is not wired yet.", command))
	fmt.Println("Graph sidecar lifecycle commands will ship with the next local_authoritative slice.")
	return fmt.Errorf("%s not wired yet", command)
}

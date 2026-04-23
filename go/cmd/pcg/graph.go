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

Current support is local-file only:

  pcg install nornicdb --from /absolute/path/to/nornicdb-headless
  pcg install nornicdb --from /absolute/path/to/nornicdb-headless --sha256 <expected-sha256>

Release download and signature verification are planned but not wired yet.
`),
		RunE: runInstallNornicDB,
	}
	installNornicDBCmd.Flags().String("from", "", "Install from an existing local NornicDB binary")
	installNornicDBCmd.Flags().String("sha256", "", "Expected SHA-256 checksum for --from")
	installNornicDBCmd.Flags().Bool("force", false, "Replace an existing managed NornicDB binary")
	installCmd.AddCommand(installNornicDBCmd)

	statusCmd := &cobra.Command{
		Use:   "status",
		Short: "Show local graph backend status for the current workspace",
		RunE:  runGraphStatus,
	}
	statusCmd.Flags().String("workspace-root", "", "Explicit workspace root for local graph status")
	graphCmd.AddCommand(statusCmd)

	graphCmd.AddCommand(&cobra.Command{
		Use:   "start",
		Short: "Start the local graph backend sidecar",
		RunE: func(cmd *cobra.Command, args []string) error {
			return graphLifecycleNotWired("pcg graph start")
		},
	})
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
	graphCmd.AddCommand(&cobra.Command{
		Use:   "upgrade",
		Short: "Upgrade the local graph backend sidecar",
		RunE: func(cmd *cobra.Command, args []string) error {
			return graphLifecycleNotWired("pcg graph upgrade")
		},
	})
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

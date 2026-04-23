package main

import (
	"errors"
	"fmt"
	"os"
	"runtime"

	"github.com/spf13/cobra"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
)

var (
	graphGetwd       = os.Getwd
	graphBuildLayout = func(workspaceRoot string) (pcglocal.Layout, error) {
		return pcglocal.BuildLayout(os.Getenv, os.UserHomeDir, runtime.GOOS, workspaceRoot)
	}
	graphReadOwnerRecord = pcglocal.ReadOwnerRecord
	graphProcessAlive    = pcglocal.ProcessAlive
	graphSocketHealthy   = pcglocal.SocketHealthy
)

type graphStatusOutput struct {
	WorkspaceRoot string `json:"workspace_root"`
	WorkspaceID   string `json:"workspace_id"`
	OwnerPresent  bool   `json:"owner_present"`
	OwnerPID      int    `json:"owner_pid,omitempty"`
	OwnerStarted  string `json:"owner_started_at,omitempty"`
	Profile       string `json:"profile,omitempty"`
	GraphBackend  string `json:"graph_backend,omitempty"`
	GraphRunning  bool   `json:"graph_running"`
	GraphPID      int    `json:"graph_pid,omitempty"`
	GraphDataDir  string `json:"graph_data_dir,omitempty"`
	GraphSocket   string `json:"graph_socket_path,omitempty"`
	GraphVersion  string `json:"graph_version,omitempty"`
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

	installCmd.AddCommand(&cobra.Command{
		Use:   "nornicdb",
		Short: "Install the local NornicDB binary",
		RunE: func(cmd *cobra.Command, args []string) error {
			return graphLifecycleNotWired("pcg install nornicdb")
		},
	})

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
	graphCmd.AddCommand(&cobra.Command{
		Use:   "stop",
		Short: "Stop the local graph backend sidecar",
		RunE: func(cmd *cobra.Command, args []string) error {
			return graphLifecycleNotWired("pcg graph stop")
		},
	})
	graphCmd.AddCommand(&cobra.Command{
		Use:   "logs",
		Short: "Show local graph backend logs",
		RunE: func(cmd *cobra.Command, args []string) error {
			return graphLifecycleNotWired("pcg graph logs")
		},
	})
	graphCmd.AddCommand(&cobra.Command{
		Use:   "upgrade",
		Short: "Upgrade the local graph backend sidecar",
		RunE: func(cmd *cobra.Command, args []string) error {
			return graphLifecycleNotWired("pcg graph upgrade")
		},
	})
}

func runGraphStatus(cmd *cobra.Command, args []string) error {
	startPath, err := graphGetwd()
	if err != nil {
		return fmt.Errorf("resolve current working directory: %w", err)
	}
	explicitRoot, err := cmd.Flags().GetString("workspace-root")
	if err != nil {
		return err
	}
	workspaceRoot, err := pcglocal.ResolveWorkspaceRoot(startPath, explicitRoot)
	if err != nil {
		return err
	}
	layout, err := graphBuildLayout(workspaceRoot)
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

func graphStatusForLayout(layout pcglocal.Layout) (graphStatusOutput, error) {
	status := graphStatusOutput{
		WorkspaceRoot: layout.WorkspaceRoot,
		WorkspaceID:   layout.WorkspaceID,
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
	status.GraphDataDir = record.GraphDataDir
	status.GraphSocket = record.GraphSocketPath
	status.GraphVersion = record.GraphVersion

	runtimeConfig, err := runtimeConfigFromOwnerRecord(record)
	if err != nil {
		return graphStatusOutput{}, err
	}
	status.Profile = string(runtimeConfig.Profile)
	status.GraphBackend = string(runtimeConfig.GraphBackend)

	if record.GraphPID > 0 && record.GraphSocketPath != "" {
		status.GraphRunning = graphProcessAlive(record.GraphPID) && graphSocketHealthy(record.GraphSocketPath)
	}

	return status, nil
}

func graphLifecycleNotWired(command string) error {
	printError(fmt.Sprintf("%q is not wired yet.", command))
	fmt.Println("Graph sidecar lifecycle commands will ship with the next local_authoritative slice.")
	return fmt.Errorf("%s not wired yet", command)
}

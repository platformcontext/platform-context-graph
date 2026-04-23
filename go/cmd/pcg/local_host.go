package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/spf13/cobra"

	"github.com/platformcontext/platform-context-graph/go/internal/buildinfo"
	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
	"github.com/platformcontext/platform-context-graph/go/internal/query"
	pgstorage "github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const localHostShutdownTimeout = 5 * time.Second

var (
	localHostBuildLayout = func(workspaceRoot string) (pcglocal.Layout, error) {
		return pcglocal.BuildLayout(os.Getenv, os.UserHomeDir, runtime.GOOS, workspaceRoot)
	}
	localHostPrepareWorkspace = func(layout pcglocal.Layout) (*pcglocal.OwnerLock, error) {
		return pcglocal.PrepareWorkspace(layout, buildinfo.AppVersion(), pcglocal.StartupDeps{
			ReclaimDeps: pcglocal.DefaultReclaimDeps(),
		})
	}
	localHostStartEmbeddedPostgres = pcglocal.StartEmbeddedPostgres
	localHostReadOwnerRecord       = pcglocal.ReadOwnerRecord
	localHostWriteOwnerRecord      = pcglocal.WriteOwnerRecord
	localHostHostname              = os.Hostname
	localHostNow                   = func() time.Time { return time.Now().UTC() }
	localHostLookPath              = exec.LookPath
	localHostProcessAlive          = pcglocal.ProcessAlive
	localHostSocketHealthy         = pcglocal.SocketHealthy
	localHostStartChildProcess     = startLocalChildProcess
	localHostWaitChildProcess      = waitLocalChildProcess
)

func init() {
	localHostCmd := &cobra.Command{
		Use:    "local-host",
		Hidden: true,
		Short:  "Internal local lightweight host supervisor",
	}

	watchCmd := &cobra.Command{
		Use:    "watch <workspace-root>",
		Args:   cobra.ExactArgs(1),
		Hidden: true,
		RunE:   runLocalHostWatch,
	}
	mcpStdioCmd := &cobra.Command{
		Use:    "mcp-stdio <workspace-root>",
		Args:   cobra.ExactArgs(1),
		Hidden: true,
		RunE:   runLocalHostMCPStdio,
	}

	localHostCmd.AddCommand(watchCmd, mcpStdioCmd)
	rootCmd.AddCommand(localHostCmd)
}

func runLocalHostWatch(cmd *cobra.Command, args []string) error {
	ctx, stop := signal.NotifyContext(cmd.Context(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	return runOwnedLocalHost(ctx, args[0], localHostModeWatch)
}

func runLocalHostMCPStdio(cmd *cobra.Command, args []string) error {
	ctx, stop := signal.NotifyContext(cmd.Context(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	layout, err := localHostBuildLayout(args[0])
	if err != nil {
		return err
	}
	if attached, err := runAttachedLocalMCPStdio(ctx, layout); attached || err != nil {
		return err
	}
	return runOwnedLocalHostWithLayout(ctx, layout, localHostModeMCPStdio)
}

type localHostMode string

const (
	localHostModeWatch    localHostMode = "watch"
	localHostModeMCPStdio localHostMode = "mcp_stdio"
)

type localHostRuntimeConfig struct {
	Profile      query.QueryProfile
	GraphBackend query.GraphBackend
}

func runOwnedLocalHost(ctx context.Context, workspaceRoot string, mode localHostMode) error {
	layout, err := localHostBuildLayout(workspaceRoot)
	if err != nil {
		return err
	}
	return runOwnedLocalHostWithLayout(ctx, layout, mode)
}

func runOwnedLocalHostWithLayout(ctx context.Context, layout pcglocal.Layout, mode localHostMode) (retErr error) {
	runtimeConfig, err := resolveLocalHostRuntimeConfig(os.Getenv)
	if err != nil {
		return err
	}
	if err := validateLocalHostRuntimeConfig(runtimeConfig); err != nil {
		return err
	}

	lock, err := localHostPrepareWorkspace(layout)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := lock.Close(); closeErr != nil && retErr == nil {
			retErr = closeErr
		}
	}()

	managedPostgres, err := localHostStartEmbeddedPostgres(ctx, layout)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := managedPostgres.Close(); closeErr != nil && retErr == nil {
			retErr = closeErr
		}
	}()

	fmt.Fprintln(os.Stderr, "bootstrapping local postgres schema...")
	if err := applyLocalBootstrap(ctx, managedPostgres.DSN); err != nil {
		return err
	}
	fmt.Fprintln(os.Stderr, "local postgres schema ready")

	hostname, err := localHostHostname()
	if err != nil {
		return fmt.Errorf("resolve hostname: %w", err)
	}
	record := pcglocal.OwnerRecord{
		PID:                os.Getpid(),
		StartedAt:          localHostNow().Format(time.RFC3339Nano),
		Hostname:           hostname,
		WorkspaceID:        layout.WorkspaceID,
		Version:            buildinfo.AppVersion(),
		PostgresPID:        managedPostgres.PID,
		PostgresPort:       managedPostgres.Port,
		PostgresDataDir:    managedPostgres.DataDir,
		PostgresSocketDir:  managedPostgres.SocketDir,
		PostgresSocketPath: managedPostgres.SocketPath,
		Profile:            string(runtimeConfig.Profile),
		GraphBackend:       string(runtimeConfig.GraphBackend),
	}
	if err := localHostWriteOwnerRecord(layout.OwnerRecordPath, record); err != nil {
		return err
	}
	defer func() {
		if err := os.Remove(layout.OwnerRecordPath); err != nil && !errors.Is(err, os.ErrNotExist) && retErr == nil {
			retErr = fmt.Errorf("remove owner record: %w", err)
		}
	}()

	ingester, err := localHostStartChildProcess("pcg-ingester", []string{"pcg-ingester", "--watch", layout.WorkspaceRoot}, localHostEnv(managedPostgres.DSN, runtimeConfig, localHostIngesterOverrides(layout, mode, runtimeConfig)))
	if err != nil {
		return err
	}
	defer func() {
		if err := stopLocalChildProcess(ingester, localHostShutdownTimeout); err != nil && retErr == nil {
			retErr = err
		}
	}()

	if mode == localHostModeWatch {
		return localHostWaitChildProcess(ctx, ingester)
	}

	mcpServer, err := localHostStartChildProcess("pcg-mcp-server", []string{"pcg-mcp-server"}, localHostEnv(managedPostgres.DSN, runtimeConfig, map[string]string{
		"PCG_MCP_TRANSPORT": "stdio",
	}))
	if err != nil {
		return err
	}
	return localHostWaitChildProcess(ctx, mcpServer)
}

func runAttachedLocalMCPStdio(ctx context.Context, layout pcglocal.Layout) (bool, error) {
	record, err := localHostReadOwnerRecord(layout.OwnerRecordPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return false, nil
		}
		return false, err
	}
	if record.WorkspaceID != "" && record.WorkspaceID != layout.WorkspaceID {
		return false, nil
	}
	if !localHostProcessAlive(record.PID) {
		return false, nil
	}
	if !localHostSocketHealthy(record.PostgresSocketPath) {
		return false, nil
	}
	if record.PostgresPort <= 0 {
		return false, fmt.Errorf("owner record missing postgres_port")
	}
	dsn := pcglocal.PostgresDSN("127.0.0.1", record.PostgresPort)
	runtimeConfig, err := runtimeConfigFromOwnerRecord(record)
	if err != nil {
		return false, err
	}
	requestedRuntimeConfig, requestedExplicit, err := requestedAttachRuntimeConfig(os.Getenv)
	if err != nil {
		return false, err
	}
	if requestedExplicit && requestedRuntimeConfig != runtimeConfig {
		return true, fmt.Errorf(
			"workspace owner is running profile %q with graph backend %q; requested profile %q with graph backend %q does not match",
			runtimeConfig.Profile,
			runtimeConfig.GraphBackend,
			requestedRuntimeConfig.Profile,
			requestedRuntimeConfig.GraphBackend,
		)
	}

	mcpServer, err := localHostStartChildProcess("pcg-mcp-server", []string{"pcg-mcp-server"}, localHostEnv(dsn, runtimeConfig, map[string]string{
		"PCG_MCP_TRANSPORT": "stdio",
	}))
	if err != nil {
		return true, err
	}
	return true, localHostWaitChildProcess(ctx, mcpServer)
}

func localHostEnv(dsn string, runtimeConfig localHostRuntimeConfig, overrides map[string]string) []string {
	values := map[string]string{
		"PCG_POSTGRES_DSN":      dsn,
		"PCG_FACT_STORE_DSN":    dsn,
		"PCG_CONTENT_STORE_DSN": dsn,
		"PCG_LISTEN_ADDR":       "127.0.0.1:0",
		"PCG_METRICS_ADDR":      "127.0.0.1:0",
		"PCG_QUERY_PROFILE":     string(runtimeConfig.Profile),
		"PCG_DISABLE_NEO4J":     "",
	}
	if runtimeConfig.Profile == query.ProfileLocalLightweight {
		values["PCG_DISABLE_NEO4J"] = "true"
	}
	if runtimeConfig.GraphBackend != "" {
		values["PCG_GRAPH_BACKEND"] = string(runtimeConfig.GraphBackend)
	}
	for key, value := range overrides {
		values[key] = value
	}
	return mergeEnvironment(pcgEnviron(), values)
}

func localHostIngesterOverrides(layout pcglocal.Layout, mode localHostMode, runtimeConfig localHostRuntimeConfig) map[string]string {
	overrides := map[string]string{
		"PCG_WATCH_PATH":        layout.WorkspaceRoot,
		"PCG_REPO_SOURCE_MODE":  "filesystem",
		"PCG_FILESYSTEM_ROOT":   layout.WorkspaceRoot,
		"PCG_FILESYSTEM_DIRECT": "true",
		"PCG_REPOS_DIR":         filepath.Join(layout.CacheDir, "repos"),
	}
	if runtimeConfig.GraphBackend != "" {
		overrides["PCG_GRAPH_BACKEND"] = string(runtimeConfig.GraphBackend)
	}
	return overrides
}

func resolveLocalHostRuntimeConfig(getenv func(string) string) (localHostRuntimeConfig, error) {
	profile := query.ProfileLocalLightweight
	rawProfile := strings.TrimSpace(getenv("PCG_QUERY_PROFILE"))
	if rawProfile != "" {
		parsedProfile, err := query.ParseQueryProfile(rawProfile)
		if err != nil {
			return localHostRuntimeConfig{}, fmt.Errorf("parse PCG_QUERY_PROFILE: %w", err)
		}
		switch parsedProfile {
		case query.ProfileLocalLightweight, query.ProfileLocalAuthoritative:
			profile = parsedProfile
		default:
			return localHostRuntimeConfig{}, fmt.Errorf(
				"local host supports only %q or %q query profiles, got %q",
				query.ProfileLocalLightweight,
				query.ProfileLocalAuthoritative,
				parsedProfile,
			)
		}
	}

	rawGraphBackend := strings.TrimSpace(getenv("PCG_GRAPH_BACKEND"))
	if profile == query.ProfileLocalLightweight {
		if rawGraphBackend != "" {
			return localHostRuntimeConfig{}, fmt.Errorf("PCG_GRAPH_BACKEND is not supported with %q", profile)
		}
		return localHostRuntimeConfig{Profile: profile}, nil
	}

	if rawGraphBackend == "" {
		return localHostRuntimeConfig{
			Profile:      profile,
			GraphBackend: query.GraphBackendNornicDB,
		}, nil
	}

	graphBackend, err := query.ParseGraphBackend(rawGraphBackend)
	if err != nil {
		return localHostRuntimeConfig{}, fmt.Errorf("parse PCG_GRAPH_BACKEND: %w", err)
	}
	return localHostRuntimeConfig{
		Profile:      profile,
		GraphBackend: graphBackend,
	}, nil
}

func validateLocalHostRuntimeConfig(runtimeConfig localHostRuntimeConfig) error {
	if runtimeConfig.Profile == query.ProfileLocalAuthoritative {
		return fmt.Errorf(
			"%q local host startup is not wired yet for graph backend %q",
			query.ProfileLocalAuthoritative,
			runtimeConfig.GraphBackend,
		)
	}
	return nil
}

func requestedAttachRuntimeConfig(getenv func(string) string) (localHostRuntimeConfig, bool, error) {
	explicit := strings.TrimSpace(getenv("PCG_QUERY_PROFILE")) != "" || strings.TrimSpace(getenv("PCG_GRAPH_BACKEND")) != ""
	if !explicit {
		return localHostRuntimeConfig{}, false, nil
	}

	runtimeConfig, err := resolveLocalHostRuntimeConfig(getenv)
	if err != nil {
		return localHostRuntimeConfig{}, false, err
	}
	return runtimeConfig, true, nil
}

func runtimeConfigFromOwnerRecord(record pcglocal.OwnerRecord) (localHostRuntimeConfig, error) {
	if strings.TrimSpace(record.Profile) == "" {
		return localHostRuntimeConfig{Profile: query.ProfileLocalLightweight}, nil
	}

	profile, err := query.ParseQueryProfile(record.Profile)
	if err != nil {
		return localHostRuntimeConfig{}, fmt.Errorf("parse owner record profile: %w", err)
	}
	if profile == query.ProfileLocalLightweight {
		return localHostRuntimeConfig{Profile: profile}, nil
	}
	if strings.TrimSpace(record.GraphBackend) == "" {
		return localHostRuntimeConfig{
			Profile:      profile,
			GraphBackend: query.GraphBackendNornicDB,
		}, nil
	}

	graphBackend, err := query.ParseGraphBackend(record.GraphBackend)
	if err != nil {
		return localHostRuntimeConfig{}, fmt.Errorf("parse owner record graph backend: %w", err)
	}
	return localHostRuntimeConfig{
		Profile:      profile,
		GraphBackend: graphBackend,
	}, nil
}

func mergeEnvironment(base []string, overrides map[string]string) []string {
	merged := make(map[string]string, len(base)+len(overrides))
	for _, entry := range base {
		for i := 0; i < len(entry); i++ {
			if entry[i] == '=' {
				merged[entry[:i]] = entry[i+1:]
				break
			}
		}
	}
	for key, value := range overrides {
		merged[key] = value
	}
	env := make([]string, 0, len(merged))
	for key, value := range merged {
		env = append(env, key+"="+value)
	}
	return env
}

func startLocalChildProcess(name string, args []string, env []string) (*exec.Cmd, error) {
	binary, err := localHostLookPath(name)
	if err != nil {
		return nil, fmt.Errorf("%s binary not found in PATH", name)
	}
	cmd := exec.Command(binary, args[1:]...)
	cmd.Args = append([]string(nil), args...)
	cmd.Env = env
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start %s: %w", name, err)
	}
	return cmd, nil
}

func waitLocalChildProcess(ctx context.Context, cmd *exec.Cmd) error {
	errc := make(chan error, 1)
	go func() {
		errc <- cmd.Wait()
	}()

	select {
	case err := <-errc:
		return err
	case <-ctx.Done():
		if err := stopLocalChildProcess(cmd, localHostShutdownTimeout); err != nil {
			return err
		}
		return nil
	}
}

func stopLocalChildProcess(cmd *exec.Cmd, timeout time.Duration) error {
	if cmd == nil || cmd.Process == nil {
		return nil
	}
	if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
		return nil
	}
	if err := cmd.Process.Signal(os.Interrupt); err != nil && !errors.Is(err, os.ErrProcessDone) {
		_ = cmd.Process.Kill()
		return fmt.Errorf("interrupt child process: %w", err)
	}

	done := make(chan error, 1)
	go func() {
		done <- cmd.Wait()
	}()

	select {
	case err := <-done:
		if err == nil || errors.Is(err, os.ErrProcessDone) {
			return nil
		}
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			return nil
		}
		return err
	case <-time.After(timeout):
		if err := cmd.Process.Kill(); err != nil && !errors.Is(err, os.ErrProcessDone) {
			return fmt.Errorf("kill child process: %w", err)
		}
		<-done
		return nil
	}
}

func applyLocalBootstrap(ctx context.Context, dsn string) error {
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return fmt.Errorf("open local postgres bootstrap connection: %w", err)
	}
	defer func() { _ = db.Close() }()

	if err := db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping local postgres bootstrap connection: %w", err)
	}
	if err := pgstorage.ApplyBootstrap(ctx, db); err != nil {
		return fmt.Errorf("apply local postgres bootstrap: %w", err)
	}
	return nil
}

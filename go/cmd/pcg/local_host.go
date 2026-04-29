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
const deferContentSearchIndexesEnv = "PCG_LOCAL_AUTHORITATIVE_DEFER_CONTENT_SEARCH_INDEXES"

var (
	localHostBuildLayout = func(workspaceRoot string) (pcglocal.Layout, error) {
		return pcglocal.BuildLayout(os.Getenv, os.UserHomeDir, runtime.GOOS, workspaceRoot)
	}
	localHostPrepareWorkspace = func(layout pcglocal.Layout) (*pcglocal.OwnerLock, error) {
		return pcglocal.PrepareWorkspace(layout, buildinfo.AppVersion(), pcglocal.StartupDeps{
			ReclaimDeps: pcglocal.ReclaimDeps{
				PIDAlive:      pcglocal.ProcessAlive,
				SocketHealthy: pcglocal.SocketHealthy,
				StopPostgres:  pcglocal.StopEmbeddedPostgres,
				GraphHealthy:  graphHealthyFromOwnerRecord,
				StopGraph:     stopRecordedLocalGraph,
			},
		})
	}
	localHostStartEmbeddedPostgres                = pcglocal.StartEmbeddedPostgres
	localHostReadOwnerRecord                      = pcglocal.ReadOwnerRecord
	localHostWriteOwnerRecord                     = pcglocal.WriteOwnerRecord
	localHostHostname                             = os.Hostname
	localHostNow                                  = func() time.Time { return time.Now().UTC() }
	localHostLookPath                             = exec.LookPath
	localHostProcessAlive                         = pcglocal.ProcessAlive
	localHostSocketHealthy                        = pcglocal.SocketHealthy
	localHostGraphHealthy                         = graphHealthyFromOwnerRecord
	localHostStartChildProcess                    = startLocalChildProcess
	localHostStartManagedGraph                    = startManagedLocalGraph
	localHostWaitChildProcess                     = waitLocalChildProcess
	localHostWaitManagedChildren                  = waitLocalHostChildren
	localHostWaitOwnerChildren                    = waitLocalHostChildrenKeepingAllowedCleanExits
	localHostApplyBootstrap                       = applyLocalBootstrap
	localHostApplyGraphBootstrap                  = applyLocalGraphBootstrap
	localHostStartProgressReporter                = startLocalHostProgressReporter
	localHostStartDeferredContentSearchIndexes    = startDeferredContentSearchIndexes
	localHostContentSearchIndexExpectedProjectors = localContentSearchIndexExpectedProjectors
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

	lock, err := localHostPrepareWorkspace(layout)
	if err != nil {
		return err
	}
	defer func() {
		if err := os.Remove(layout.OwnerRecordPath); err != nil && !errors.Is(err, os.ErrNotExist) && retErr == nil {
			retErr = fmt.Errorf("remove owner record: %w", err)
		}
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
	if err := localHostApplyBootstrap(ctx, managedPostgres.DSN); err != nil {
		return err
	}
	fmt.Fprintln(os.Stderr, "local postgres schema ready")

	var managedGraph *managedLocalGraph
	if runtimeConfig.Profile == query.ProfileLocalAuthoritative {
		managedGraph, err = localHostStartManagedGraph(ctx, layout, runtimeConfig)
		if err != nil {
			return err
		}
		defer func() {
			if err := stopManagedLocalGraph(managedGraph, localGraphShutdownTimeout); err != nil && retErr == nil {
				retErr = err
			}
		}()
		fmt.Fprintln(os.Stderr, "bootstrapping local graph schema...")
		if err := localHostApplyGraphBootstrap(ctx, runtimeConfig, managedGraph); err != nil {
			return err
		}
		fmt.Fprintln(os.Stderr, "local graph schema ready")
	}

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
		GraphAddress:       graphAddress(managedGraph),
		GraphPID:           graphPID(managedGraph),
		GraphBoltPort:      graphBoltPort(managedGraph),
		GraphHTTPPort:      graphHTTPPort(managedGraph),
		GraphDataDir:       graphDataDir(managedGraph),
		GraphVersion:       graphVersion(managedGraph),
		GraphUsername:      graphUsername(managedGraph),
		GraphPassword:      graphPassword(managedGraph),
	}
	if err := localHostWriteOwnerRecord(layout.OwnerRecordPath, record); err != nil {
		return err
	}

	if runtimeConfig.Profile == query.ProfileLocalAuthoritative && deferContentSearchIndexes(os.Getenv) {
		expectedProjectors, err := localHostContentSearchIndexExpectedProjectors(layout.WorkspaceRoot)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: deferred content search index maintainer unavailable: discover workspace repos: %v\n", err)
		} else {
			stopDeferredIndexes, err := localHostStartDeferredContentSearchIndexes(ctx, managedPostgres.DSN, expectedProjectors)
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: deferred content search index maintainer unavailable: %v\n", err)
			} else {
				defer func() {
					if err := stopDeferredIndexes(); err != nil && retErr == nil {
						retErr = fmt.Errorf("stop deferred content search index maintainer: %w", err)
					}
				}()
			}
		}
	}

	children := make([]localHostChild, 0, 3)

	if runtimeConfig.Profile == query.ProfileLocalAuthoritative {
		reducerCmd, err := localHostStartChildProcess(
			"pcg-reducer",
			[]string{"pcg-reducer"},
			localHostEnv(managedPostgres.DSN, runtimeConfig, managedGraph, nil),
		)
		if err != nil {
			return err
		}
		defer func() {
			if err := stopLocalChildProcess(reducerCmd, localHostShutdownTimeout); err != nil && retErr == nil {
				retErr = err
			}
		}()
		children = append(children, localHostChild{name: "pcg-reducer", cmd: reducerCmd})
	}

	ingester, err := localHostStartChildProcess("pcg-ingester", []string{"pcg-ingester", "--watch", layout.WorkspaceRoot}, localHostEnv(managedPostgres.DSN, runtimeConfig, managedGraph, localHostIngesterOverrides(layout, mode, runtimeConfig)))
	if err != nil {
		return err
	}
	defer func() {
		if err := stopLocalChildProcess(ingester, localHostShutdownTimeout); err != nil && retErr == nil {
			retErr = err
		}
	}()
	children = append(children, localHostChild{name: "pcg-ingester", cmd: ingester})

	if mode == localHostModeWatch {
		stopProgress, progressErr := localHostStartProgressReporter(
			ctx,
			layout.WorkspaceRoot,
			managedPostgres.DSN,
			runtimeConfig,
		)
		if progressErr != nil {
			fmt.Fprintf(os.Stderr, "warning: local progress reporter unavailable: %v\n", progressErr)
		} else {
			defer func() {
				if err := stopProgress(); err != nil && retErr == nil {
					retErr = fmt.Errorf("stop local progress reporter: %w", err)
				}
			}()
		}
	}

	if mode == localHostModeWatch && runtimeConfig.Profile == query.ProfileLocalAuthoritative {
		return localHostWaitOwnerChildren(ctx, children, map[string]struct{}{
			"pcg-ingester": {},
		})
	}
	if mode == localHostModeWatch {
		return localHostWaitManagedChildren(ctx, children, "")
	}

	mcpServer, err := localHostStartChildProcess("pcg-mcp-server", []string{"pcg-mcp-server"}, localHostEnv(managedPostgres.DSN, runtimeConfig, managedGraph, map[string]string{
		"PCG_MCP_TRANSPORT": "stdio",
	}))
	if err != nil {
		return err
	}
	defer func() {
		if err := stopLocalChildProcess(mcpServer, localHostShutdownTimeout); err != nil && retErr == nil {
			retErr = err
		}
	}()
	children = append(children, localHostChild{name: "pcg-mcp-server", cmd: mcpServer})
	return localHostWaitManagedChildren(ctx, children, "pcg-mcp-server")
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
	if runtimeConfig.Profile == query.ProfileLocalAuthoritative && !localHostGraphHealthy(record) {
		return true, fmt.Errorf(
			"workspace owner is running profile %q with graph backend %q, but the graph backend is unhealthy; run pcg graph status or restart the workspace owner",
			runtimeConfig.Profile,
			runtimeConfig.GraphBackend,
		)
	}

	mcpServer, err := localHostStartChildProcess("pcg-mcp-server", []string{"pcg-mcp-server"}, localHostEnv(dsn, runtimeConfig, managedGraphFromRecord(record), map[string]string{
		"PCG_MCP_TRANSPORT": "stdio",
	}))
	if err != nil {
		return true, err
	}
	return true, localHostWaitChildProcess(ctx, mcpServer)
}

func localHostEnv(dsn string, runtimeConfig localHostRuntimeConfig, graph *managedLocalGraph, overrides map[string]string) []string {
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
	for key, value := range graphEnvOverrides(graph) {
		values[key] = value
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

func applyLocalBootstrap(ctx context.Context, dsn string) error {
	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return fmt.Errorf("open local postgres bootstrap connection: %w", err)
	}
	defer func() { _ = db.Close() }()

	if err := db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping local postgres bootstrap connection: %w", err)
	}
	if err := pgstorage.ApplyDefinitions(ctx, db, localBootstrapDefinitions(os.Getenv)); err != nil {
		return fmt.Errorf("apply local postgres bootstrap: %w", err)
	}
	return nil
}

func localBootstrapDefinitions(getenv func(string) string) []pgstorage.Definition {
	if deferContentSearchIndexes(getenv) {
		return pgstorage.BootstrapDefinitionsWithoutContentSearchIndexes()
	}
	return pgstorage.BootstrapDefinitions()
}

func deferContentSearchIndexes(getenv func(string) string) bool {
	if getenv == nil {
		return false
	}
	raw := strings.TrimSpace(getenv(deferContentSearchIndexesEnv))
	return raw == "1" || strings.EqualFold(raw, "true") || strings.EqualFold(raw, "yes")
}

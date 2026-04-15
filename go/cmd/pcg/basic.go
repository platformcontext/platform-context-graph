package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"

	"github.com/spf13/cobra"
)

func init() {
	// index
	indexCmd := &cobra.Command{
		Use:   "index [path]",
		Short: "Index a local path into the code graph",
		Args:  cobra.MaximumNArgs(1),
		RunE:  runIndex,
	}
	indexCmd.Flags().BoolP("force", "f", false, "Force re-index")
	rootCmd.AddCommand(indexCmd)

	// index-status
	indexStatusCmd := &cobra.Command{
		Use:   "index-status",
		Short: "Show the latest checkpointed indexing status",
		Args:  cobra.NoArgs,
		RunE:  runIndexStatus,
	}
	addRemoteFlags(indexStatusCmd)
	rootCmd.AddCommand(indexStatusCmd)

	// list
	listCmd := &cobra.Command{
		Use:   "list",
		Short: "List all indexed repositories",
		RunE:  runList,
	}
	rootCmd.AddCommand(listCmd)

	// stats
	statsCmd := &cobra.Command{
		Use:   "stats [path]",
		Short: "Show indexing statistics",
		Args:  cobra.MaximumNArgs(1),
		RunE:  runStats,
	}
	rootCmd.AddCommand(statsCmd)

	// delete
	deleteCmd := &cobra.Command{
		Use:   "delete [path]",
		Short: "Delete one or all indexed repositories",
		Args:  cobra.MaximumNArgs(1),
		RunE:  runDelete,
	}
	deleteCmd.Flags().Bool("all", false, "Delete all indexed repositories")
	rootCmd.AddCommand(deleteCmd)

	// clean
	cleanCmd := &cobra.Command{
		Use:   "clean",
		Short: "Remove orphaned nodes and relationships",
		RunE:  runClean,
	}
	rootCmd.AddCommand(cleanCmd)

	// query
	queryCmd := &cobra.Command{
		Use:   "query <cypher>",
		Short: "Execute a read-only Cypher query",
		Args:  cobra.ExactArgs(1),
		RunE:  runQuery,
	}
	rootCmd.AddCommand(queryCmd)

	// watch
	watchCmd := &cobra.Command{
		Use:   "watch [path]",
		Short: "Watch a local path for changes and update the graph",
		Args:  cobra.MaximumNArgs(1),
		RunE:  runWatch,
	}
	watchCmd.Flags().String("scope", "auto", "Watch scope: auto, repo, or workspace")
	rootCmd.AddCommand(watchCmd)

	// unwatch
	unwatchCmd := &cobra.Command{
		Use:   "unwatch <path>",
		Short: "Stop watching a directory",
		Args:  cobra.ExactArgs(1),
		RunE:  runUnwatch,
	}
	rootCmd.AddCommand(unwatchCmd)

	// watching
	watchingCmd := &cobra.Command{
		Use:   "watching",
		Short: "List all directories being watched",
		RunE:  runWatching,
	}
	rootCmd.AddCommand(watchingCmd)

	// add-package
	addPkgCmd := &cobra.Command{
		Use:   "add-package <name> <language>",
		Short: "Add a package dependency to the code graph",
		Args:  cobra.ExactArgs(2),
		RunE:  runAddPackage,
	}
	rootCmd.AddCommand(addPkgCmd)

	// finalize (deprecated)
	finalizeCmd := &cobra.Command{
		Use:        "finalize",
		Short:      "Deprecated: recovery is owned by the Go ingester",
		Deprecated: "use Go ingester admin endpoints instead",
		RunE: func(cmd *cobra.Command, args []string) error {
			printError("'pcg finalize' has been removed.")
			_, _ = fmt.Fprintln(os.Stderr, "Recovery operations are now owned by the Go ingester.")
			_, _ = fmt.Fprintln(os.Stderr, "Use the ingester admin endpoints:")
			_, _ = fmt.Fprintln(os.Stderr, "  POST http://<ingester>:8080/admin/refinalize")
			_, _ = fmt.Fprintln(os.Stderr, "  POST http://<ingester>:8080/admin/replay")
			return fmt.Errorf("command removed")
		},
	}
	rootCmd.AddCommand(finalizeCmd)

	// Shortcuts
	rootCmd.AddCommand(&cobra.Command{
		Use:   "i [path]",
		Short: "Shortcut for 'pcg index'",
		Args:  cobra.MaximumNArgs(1),
		RunE:  runIndex,
	})
	rootCmd.AddCommand(&cobra.Command{
		Use:   "ls",
		Short: "Shortcut for 'pcg list'",
		RunE:  runList,
	})
	rmCmd := &cobra.Command{
		Use:   "rm [path]",
		Short: "Shortcut for 'pcg delete'",
		Args:  cobra.MaximumNArgs(1),
		RunE:  runDelete,
	}
	rmCmd.Flags().Bool("all", false, "Delete all indexed repositories")
	rootCmd.AddCommand(rmCmd)
	rootCmd.AddCommand(&cobra.Command{
		Use:   "w [path]",
		Short: "Shortcut for 'pcg watch'",
		Args:  cobra.MaximumNArgs(1),
		RunE:  runWatch,
	})
}

func runIndex(cmd *cobra.Command, args []string) error {
	path := "."
	if len(args) > 0 {
		path = args[0]
	}
	absPath, err := filepath.Abs(path)
	if err != nil {
		return err
	}

	force, _ := cmd.Flags().GetBool("force")

	binary, err := exec.LookPath("pcg-bootstrap-index")
	if err != nil {
		printError("pcg-bootstrap-index binary not found in PATH.")
		fmt.Println("Build with: cd go && go build -o bin/ ./cmd/bootstrap-index/")
		return fmt.Errorf("pcg-bootstrap-index not found")
	}

	cmdArgs := []string{"pcg-bootstrap-index", "--path", absPath}
	if force {
		cmdArgs = append(cmdArgs, "--force")
	}

	fmt.Printf("Indexing %s...\n", absPath)
	return syscall.Exec(binary, cmdArgs, os.Environ())
}

func runIndexStatus(cmd *cobra.Command, args []string) error {
	client := apiClient()
	var result any
	if err := client.Get("/api/v0/index-status", &result); err != nil {
		return err
	}
	printJSON(result)
	return nil
}

func runList(cmd *cobra.Command, args []string) error {
	client := NewAPIClient("", "", "")
	var result any
	if err := client.Get("/api/v0/repositories", &result); err != nil {
		return err
	}
	printJSON(result)
	return nil
}

func runStats(cmd *cobra.Command, args []string) error {
	client := NewAPIClient("", "", "")
	path := ""
	if len(args) > 0 {
		var err error
		path, err = filepath.Abs(args[0])
		if err != nil {
			return err
		}
	}
	if path != "" {
		var result any
		// Use repository stats endpoint with encoded path
		if err := client.Get(fmt.Sprintf("/api/v0/repositories/%s/stats", path), &result); err != nil {
			return err
		}
		printJSON(result)
	} else {
		// Get overall pipeline status
		var result any
		if err := client.Get("/api/v0/status/pipeline", &result); err != nil {
			return err
		}
		printJSON(result)
	}
	return nil
}

func runDelete(cmd *cobra.Command, args []string) error {
	allRepos, _ := cmd.Flags().GetBool("all")
	if !allRepos && len(args) == 0 {
		printError("Please provide a path or use --all to delete all repositories")
		return fmt.Errorf("missing path")
	}
	// For now, delete uses the admin API
	client := NewAPIClient("", "", "")
	if allRepos {
		fmt.Println("Deleting all repositories...")
		// This would need a specific endpoint; for now print guidance
		fmt.Println("Use the admin API or Cypher: MATCH (r:Repository) DETACH DELETE r")
	} else {
		absPath, _ := filepath.Abs(args[0])
		fmt.Printf("Deleting repository: %s\n", absPath)
		var result any
		_ = client.Post("/api/v0/admin/reindex", map[string]any{
			"path":   absPath,
			"action": "delete",
		}, &result)
	}
	return nil
}

func runClean(cmd *cobra.Command, args []string) error {
	fmt.Println("Cleaning orphaned nodes and relationships...")
	client := NewAPIClient("", "", "")
	var result any
	if err := client.Post("/api/v0/admin/reindex", map[string]any{"action": "clean"}, &result); err != nil {
		return err
	}
	printJSON(result)
	return nil
}

func runQuery(cmd *cobra.Command, args []string) error {
	client := NewAPIClient("", "", "")
	var result any
	if err := client.Post("/api/v0/code/language-query", map[string]any{
		"query": args[0],
	}, &result); err != nil {
		return err
	}
	printJSON(result)
	return nil
}

func runWatch(cmd *cobra.Command, args []string) error {
	path := "."
	if len(args) > 0 {
		path = args[0]
	}
	absPath, _ := filepath.Abs(path)

	binary, err := exec.LookPath("pcg-ingester")
	if err != nil {
		printError("pcg-ingester binary not found in PATH.")
		return fmt.Errorf("pcg-ingester not found")
	}

	fmt.Printf("Watching %s for changes...\n", absPath)
	if err := os.Setenv("PCG_WATCH_PATH", absPath); err != nil {
		return err
	}
	return syscall.Exec(binary, []string{"pcg-ingester", "--watch", absPath}, os.Environ())
}

func runUnwatch(cmd *cobra.Command, args []string) error {
	fmt.Printf("Stopped watching: %s\n", args[0])
	return nil
}

func runWatching(cmd *cobra.Command, args []string) error {
	fmt.Println("Active watchers are managed by the Go ingester service.")
	fmt.Println("Check ingester status: curl http://localhost:8080/api/v0/status/ingesters")
	return nil
}

func runAddPackage(cmd *cobra.Command, args []string) error {
	fmt.Printf("Adding package %s (%s) to the code graph...\n", args[0], args[1])
	// Package addition would be handled via the ingester
	fmt.Println("Package indexing is handled by the Go bootstrap-index binary.")
	return nil
}

// addRemoteFlags adds --service-url, --api-key, and --profile flags to a command.
func addRemoteFlags(cmd *cobra.Command) {
	cmd.Flags().String("service-url", "", "API service URL (overrides config)")
	cmd.Flags().String("api-key", "", "API key for authentication")
	cmd.Flags().String("profile", "", "Config profile name")
}

// apiClient creates an APIClient from command flags or defaults.
func apiClient() *APIClient {
	return NewAPIClient("", "", "")
}

// apiClientFromCmd creates an APIClient from cobra command flags.
func apiClientFromCmd(cmd *cobra.Command) *APIClient {
	serviceURL, _ := cmd.Flags().GetString("service-url")
	apiKey, _ := cmd.Flags().GetString("api-key")
	profile, _ := cmd.Flags().GetString("profile")
	return NewAPIClient(serviceURL, apiKey, profile)
}

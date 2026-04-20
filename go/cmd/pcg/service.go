package main

import (
	"fmt"
	"os"
	"os/exec"
	"syscall"

	"github.com/spf13/cobra"
)

var mcpCmd = &cobra.Command{
	Use:   "mcp",
	Short: "MCP server commands",
}

var apiCmd = &cobra.Command{
	Use:   "api",
	Short: "HTTP API server commands",
}

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Combined service commands",
}

func init() {
	rootCmd.AddCommand(mcpCmd)
	rootCmd.AddCommand(apiCmd)
	rootCmd.AddCommand(serveCmd)

	// mcp start
	mcpStartCmd := &cobra.Command{
		Use:   "start",
		Short: "Start the PlatformContextGraph MCP server",
		RunE:  runMCPStart,
	}
	mcpStartCmd.Flags().StringP("transport", "t", "stdio", "Transport mode: stdio or sse")
	mcpStartCmd.Flags().String("host", "0.0.0.0", "Host to bind SSE server")
	mcpStartCmd.Flags().IntP("port", "p", 8080, "Port for SSE server")
	mcpCmd.AddCommand(mcpStartCmd)

	// mcp setup
	mcpSetupCmd := &cobra.Command{
		Use:   "setup",
		Short: "Configure IDE and CLI MCP integrations",
		RunE:  runMCPSetup,
	}
	mcpCmd.AddCommand(mcpSetupCmd)

	// mcp tools
	mcpToolsCmd := &cobra.Command{
		Use:   "tools",
		Short: "List available MCP tools",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Println("MCP tools are served by the Go MCP server.")
			fmt.Println("Start the server with 'pcg mcp start' and connect via your IDE.")
		},
	}
	mcpCmd.AddCommand(mcpToolsCmd)

	// api start
	apiStartCmd := &cobra.Command{
		Use:   "start",
		Short: "Start the HTTP API server",
		RunE:  runAPIStart,
	}
	apiStartCmd.Flags().String("host", "127.0.0.1", "Host to bind")
	apiStartCmd.Flags().IntP("port", "p", 8080, "Port for the API server")
	apiCmd.AddCommand(apiStartCmd)

	// serve start
	serveStartCmd := &cobra.Command{
		Use:   "start",
		Short: "Start the combined HTTP API and MCP service",
		RunE:  runServeStart,
	}
	serveStartCmd.Flags().String("host", "0.0.0.0", "Host to bind")
	serveStartCmd.Flags().IntP("port", "p", 8080, "Port for the combined service")
	serveCmd.AddCommand(serveStartCmd)

	// Shortcut: pcg m -> mcp setup
	mAlias := &cobra.Command{
		Use:    "m",
		Short:  "Shortcut for 'pcg mcp setup'",
		Hidden: false,
		RunE:   runMCPSetup,
	}
	rootCmd.AddCommand(mAlias)

	// Shortcut: pcg start -> mcp start (deprecated)
	startAlias := &cobra.Command{
		Use:        "start",
		Short:      "Deprecated: use 'pcg mcp start' instead",
		Deprecated: "use 'pcg mcp start' instead",
		RunE:       runMCPStart,
	}
	rootCmd.AddCommand(startAlias)
}

func runMCPStart(cmd *cobra.Command, args []string) error {
	transport, _ := cmd.Flags().GetString("transport")
	host, _ := cmd.Flags().GetString("host")
	port, _ := cmd.Flags().GetInt("port")

	binary, err := exec.LookPath("pcg-mcp-server")
	if err != nil {
		printError("pcg-mcp-server binary not found in PATH.")
		fmt.Println("\nThe MCP server is a Go binary. Ensure:")
		fmt.Println("  1. Go binaries are built: cd go && make build")
		fmt.Println("  2. Binary is in PATH: export PATH=$PATH:$(pwd)/go/bin")
		return fmt.Errorf("pcg-mcp-server not found")
	}

	if err := os.Setenv("PCG_MCP_TRANSPORT", transport); err != nil {
		return err
	}
	if transport == "sse" {
		if err := os.Setenv("PCG_MCP_ADDR", fmt.Sprintf("%s:%d", host, port)); err != nil {
			return err
		}
	}

	fmt.Printf("Starting PlatformContextGraph MCP Server (%s transport)...\n", transport)
	return syscall.Exec(binary, []string{"pcg-mcp-server"}, os.Environ())
}

func runMCPSetup(cmd *cobra.Command, args []string) error {
	fmt.Println("MCP Client Setup")
	fmt.Println("Configure your IDE or CLI tool to use PlatformContextGraph.")
	fmt.Println()
	fmt.Println("Add this to your MCP client configuration:")
	fmt.Println()
	fmt.Println(`  {`)
	fmt.Println(`    "mcpServers": {`)
	fmt.Println(`      "platform-context-graph": {`)
	fmt.Println(`        "command": "pcg",`)
	fmt.Println(`        "args": ["mcp", "start"]`)
	fmt.Println(`      }`)
	fmt.Println(`    }`)
	fmt.Println(`  }`)
	return nil
}

func runAPIStart(cmd *cobra.Command, args []string) error {
	host, _ := cmd.Flags().GetString("host")
	port, _ := cmd.Flags().GetInt("port")

	binary, err := exec.LookPath("pcg-api")
	if err != nil {
		printError("pcg-api binary not found in PATH.")
		return fmt.Errorf("pcg-api not found")
	}

	if err := os.Setenv("PCG_API_ADDR", fmt.Sprintf("%s:%d", host, port)); err != nil {
		return err
	}
	fmt.Printf("Starting PlatformContextGraph HTTP API on %s:%d...\n", host, port)
	return syscall.Exec(binary, []string{"pcg-api"}, os.Environ())
}

func runServeStart(cmd *cobra.Command, args []string) error {
	host, _ := cmd.Flags().GetString("host")
	port, _ := cmd.Flags().GetInt("port")

	binary, err := exec.LookPath("pcg-api")
	if err != nil {
		printError("pcg-api binary not found in PATH.")
		return fmt.Errorf("pcg-api not found")
	}

	if err := os.Setenv("PCG_API_ADDR", fmt.Sprintf("%s:%d", host, port)); err != nil {
		return err
	}
	fmt.Printf("Starting PlatformContextGraph service (HTTP API + MCP) on %s:%d...\n", host, port)
	return syscall.Exec(binary, []string{"pcg-api"}, os.Environ())
}

package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var (
	globalDatabase string
	globalVisual   bool
)

var rootCmd = &cobra.Command{
	Use:   "pcg",
	Short: "PlatformContextGraph -- code-to-cloud context graph",
	Long: `PlatformContextGraph is both an MCP server and a CLI toolkit for code analysis.

For MCP Server Mode (AI assistants):
  1. Run 'pcg mcp setup' to configure your IDE
  2. Run 'pcg mcp start' to launch the server

For CLI Toolkit Mode (direct usage):
  pcg index .     -- Index your current directory
  pcg list        -- List indexed repositories

Run 'pcg help' to see all available commands.`,
	SilenceUsage:  true,
	SilenceErrors: true,
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		if globalDatabase != "" {
			if err := os.Setenv("PCG_RUNTIME_DB_TYPE", globalDatabase); err != nil {
				return err
			}
		}
		return nil
	},
}

func init() {
	rootCmd.PersistentFlags().StringVar(&globalDatabase, "database", "", "Temporarily override database backend")
	rootCmd.PersistentFlags().BoolVarP(&globalVisual, "visual", "V", false, "Show results as interactive graph visualization")

	rootCmd.AddCommand(versionCmd)
	rootCmd.AddCommand(helpCmd)
	rootCmd.AddCommand(doctorCmd)
}

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Show the installed application version",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("PlatformContextGraph %s\n", version)
	},
}

var helpCmd = &cobra.Command{
	Use:   "help",
	Short: "Show the main help message",
	RunE:  func(cmd *cobra.Command, args []string) error { return rootCmd.Help() },
}

var doctorCmd = &cobra.Command{
	Use:   "doctor",
	Short: "Run diagnostics to check system health and configuration",
	RunE:  runDoctor,
}

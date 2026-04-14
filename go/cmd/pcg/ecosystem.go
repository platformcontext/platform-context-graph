package main

import (
	"fmt"

	"github.com/spf13/cobra"
)

var ecosystemCmd = &cobra.Command{
	Use:   "ecosystem",
	Short: "Ecosystem-wide analysis (migrated to Go)",
}

func init() {
	rootCmd.AddCommand(ecosystemCmd)

	ecosystemCmd.AddCommand(&cobra.Command{
		Use:   "index",
		Short: "Ecosystem indexing is now handled by the Go ingester",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Println("Ecosystem indexing has been migrated to the Go ingester service.")
			fmt.Println("Use: pcg index <path> or run the ingester directly.")
			return nil
		},
	})

	ecosystemCmd.AddCommand(&cobra.Command{
		Use:   "status",
		Short: "Show ecosystem indexing status",
		RunE: func(cmd *cobra.Command, args []string) error {
			client := NewAPIClient("", "", "")
			var result any
			if err := client.Get("/api/v0/status/pipeline", &result); err != nil {
				return err
			}
			printJSON(result)
			return nil
		},
	})

	ecosystemCmd.AddCommand(&cobra.Command{
		Use:   "overview",
		Short: "Show ecosystem overview",
		RunE: func(cmd *cobra.Command, args []string) error {
			client := NewAPIClient("", "", "")
			var result any
			if err := client.Get("/api/v0/repositories", &result); err != nil {
				return err
			}
			printJSON(result)
			return nil
		},
	})
}

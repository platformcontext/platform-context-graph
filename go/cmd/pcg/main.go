package main

import (
	"fmt"
	"os"
)

// version is set at build time via ldflags.
var version = "dev"

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

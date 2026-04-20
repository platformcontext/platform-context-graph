package buildinfo

import "strings"

// Version is injected at build time via ldflags. Source builds default to dev.
var Version = "dev"

// AppVersion returns the normalized application version used by runtime and API
// surfaces. Empty or whitespace-only values collapse to "dev".
func AppVersion() string {
	version := strings.TrimSpace(Version)
	if version == "" {
		return "dev"
	}
	return version
}

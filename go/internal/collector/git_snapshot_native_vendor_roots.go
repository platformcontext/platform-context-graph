package collector

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/collector/discovery"
)

const vendorRootsConfigRelPath = ".pcg/vendor-roots.json"

type vendorRootsConfig struct {
	VendorRoots []vendorRootRule `json:"vendor_roots"`
	KeepRoots   []vendorRootRule `json:"keep_roots"`
}

type vendorRootRule struct {
	Path   string `json:"path"`
	Reason string `json:"reason,omitempty"`
}

func discoveryOptionsWithVendorRootsConfig(
	repoPath string,
	opts discovery.Options,
) (discovery.Options, error) {
	configPath := filepath.Join(repoPath, vendorRootsConfigRelPath)
	contents, err := os.ReadFile(configPath)
	if err != nil {
		if os.IsNotExist(err) {
			return opts, nil
		}
		return discovery.Options{}, fmt.Errorf("read %s: %w", vendorRootsConfigRelPath, err)
	}

	var config vendorRootsConfig
	decoder := json.NewDecoder(bytes.NewReader(contents))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&config); err != nil {
		return discovery.Options{}, fmt.Errorf("parse %s: %w", vendorRootsConfigRelPath, err)
	}

	for _, root := range config.VendorRoots {
		pattern, err := validateVendorRootPattern(root.Path)
		if err != nil {
			return discovery.Options{}, fmt.Errorf("validate %s vendor_roots path %q: %w", vendorRootsConfigRelPath, root.Path, err)
		}
		reason := strings.TrimSpace(root.Reason)
		if reason == "" {
			reason = "user-vendor-root"
		}
		opts.IgnoredPathGlobs = append(opts.IgnoredPathGlobs, discovery.PathGlobRule{
			Pattern: pattern,
			Reason:  reason,
		})
	}
	for _, root := range config.KeepRoots {
		pattern, err := validateVendorRootPattern(root.Path)
		if err != nil {
			return discovery.Options{}, fmt.Errorf("validate %s keep_roots path %q: %w", vendorRootsConfigRelPath, root.Path, err)
		}
		opts.PreservedPathGlobs = append(opts.PreservedPathGlobs, pattern)
	}
	return opts, nil
}

func validateVendorRootPattern(pattern string) (string, error) {
	pattern = strings.TrimSpace(filepath.ToSlash(pattern))
	if pattern == "" {
		return "", errors.New("path is required")
	}
	if strings.HasPrefix(pattern, "/") {
		return "", errors.New("path must be repository-relative")
	}
	for strings.HasPrefix(pattern, "./") {
		pattern = strings.TrimPrefix(pattern, "./")
	}
	for _, segment := range strings.Split(pattern, "/") {
		if segment == ".." {
			return "", errors.New("path must not contain '..'")
		}
	}
	cleaned := filepath.ToSlash(filepath.Clean(pattern))
	if cleaned == "." || cleaned == "" {
		return "", errors.New("path is required")
	}
	if strings.HasSuffix(pattern, "/**") && !strings.HasSuffix(cleaned, "/**") {
		cleaned += "/**"
	}
	return cleaned, nil
}

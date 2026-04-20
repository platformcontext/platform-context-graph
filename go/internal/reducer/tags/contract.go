package tags

import (
	"fmt"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

// RuntimeContract captures the accepted tag-normalization reducer scaffold.
type RuntimeContract struct {
	Components         []string
	CanonicalKeyspaces []reducer.GraphProjectionKeyspace
}

// DefaultRuntimeContract returns the accepted tag-normalization scaffold.
func DefaultRuntimeContract() RuntimeContract {
	return RuntimeContract{
		Components: []string{
			"normalizer",
		},
		CanonicalKeyspaces: []reducer.GraphProjectionKeyspace{
			reducer.GraphProjectionKeyspaceCloudResourceUID,
		},
	}
}

// Validate checks that the scaffold does not contain blank ownership metadata.
func (c RuntimeContract) Validate() error {
	if len(c.Components) == 0 {
		return fmt.Errorf("components must not be empty")
	}
	if len(c.CanonicalKeyspaces) == 0 {
		return fmt.Errorf("canonical_keyspaces must not be empty")
	}
	for _, component := range c.Components {
		if strings.TrimSpace(component) == "" {
			return fmt.Errorf("components must not contain blank values")
		}
	}
	for _, keyspace := range c.CanonicalKeyspaces {
		if strings.TrimSpace(string(keyspace)) == "" {
			return fmt.Errorf("canonical_keyspaces must not contain blank values")
		}
	}
	return nil
}

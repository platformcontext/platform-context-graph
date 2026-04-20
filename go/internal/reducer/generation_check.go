package reducer

import "context"

// GenerationFreshnessCheck reports whether the given generation is still
// the active generation for the scope. Returns (true, nil) if current,
// (false, nil) if superseded, or (false, err) on lookup failure.
type GenerationFreshnessCheck func(ctx context.Context, scopeID, generationID string) (bool, error)

package pcglocal

import (
	"errors"
	"fmt"
	"os"
)

var (
	// ErrWorkspaceOwnerActive indicates stale owner metadata still points to a live owner.
	ErrWorkspaceOwnerActive = errors.New("workspace owner still active")
	// ErrEmbeddedPostgresActive indicates the embedded Postgres process still appears to be alive.
	ErrEmbeddedPostgresActive = errors.New("embedded postgres still active")
	// ErrInvalidOwnerRecord indicates owner metadata is corrupt or inconsistent with the workspace.
	ErrInvalidOwnerRecord = errors.New("invalid owner record")
)

// ReclaimDeps injects process and socket health checks for reclaim decisions.
type ReclaimDeps struct {
	PIDAlive      func(pid int) bool
	SocketHealthy func(path string) bool
	StopPostgres  func(dataDir string) error
}

// ValidateOrReclaimOwner decides whether an existing owner record can be reclaimed.
//
// This helper assumes the caller already holds owner.lock, so the remaining hazards
// are stale metadata and stale child processes rather than lock split-brain.
func ValidateOrReclaimOwner(layout Layout, currentVersion string, deps ReclaimDeps) error {
	record, err := ReadOwnerRecord(layout.OwnerRecordPath)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return err
	}
	if layout.WorkspaceID != "" && record.WorkspaceID != "" && record.WorkspaceID != layout.WorkspaceID {
		return fmt.Errorf("%w: record_workspace_id=%q layout_workspace_id=%q", ErrInvalidOwnerRecord, record.WorkspaceID, layout.WorkspaceID)
	}

	if deps.pidAlive(record.PID) || deps.socketHealthy(record.SocketPath) {
		return fmt.Errorf(
			"%w: pid=%d socket=%q record_version=%q current_version=%q",
			ErrWorkspaceOwnerActive,
			record.PID,
			record.SocketPath,
			record.Version,
			currentVersion,
		)
	}

	if deps.pidAlive(record.PostgresPID) || deps.socketHealthy(record.PostgresSocketPath) {
		if record.PostgresDataDir == "" {
			return fmt.Errorf("%w: postgres_data_dir is required when postgres appears active", ErrInvalidOwnerRecord)
		}
		if deps.StopPostgres == nil {
			return fmt.Errorf("%w: no stop function configured for data_dir=%q", ErrEmbeddedPostgresActive, record.PostgresDataDir)
		}
		if err := deps.StopPostgres(record.PostgresDataDir); err != nil {
			return fmt.Errorf("stop stale embedded postgres: %w", err)
		}
		if deps.pidAlive(record.PostgresPID) || deps.socketHealthy(record.PostgresSocketPath) {
			return fmt.Errorf("%w: pid=%d socket=%q data_dir=%q", ErrEmbeddedPostgresActive, record.PostgresPID, record.PostgresSocketPath, record.PostgresDataDir)
		}
	}

	if err := os.Remove(layout.OwnerRecordPath); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("remove stale owner record: %w", err)
	}
	return nil
}

func (d ReclaimDeps) pidAlive(pid int) bool {
	if d.PIDAlive == nil || pid <= 0 {
		return false
	}
	return d.PIDAlive(pid)
}

func (d ReclaimDeps) socketHealthy(path string) bool {
	if d.SocketHealthy == nil || path == "" {
		return false
	}
	return d.SocketHealthy(path)
}

package main

import (
	"testing"
	"time"
)

func TestLoadReducerQueueConfigUsesDefaults(t *testing.T) {
	t.Parallel()

	cfg, err := loadReducerQueueConfig(func(string) string { return "" })
	if err != nil {
		t.Fatalf("loadReducerQueueConfig() error = %v, want nil", err)
	}

	if got, want := cfg.RetryDelay, 30*time.Second; got != want {
		t.Fatalf("retryDelay = %v, want %v", got, want)
	}
	if got, want := cfg.MaxAttempts, 3; got != want {
		t.Fatalf("maxAttempts = %d, want %d", got, want)
	}
}

func TestLoadReducerQueueConfigReadsEnvOverrides(t *testing.T) {
	t.Parallel()

	cfg, err := loadReducerQueueConfig(func(name string) string {
		switch name {
		case reducerRetryDelayEnv:
			return "2m"
		case reducerMaxAttemptsEnv:
			return "5"
		default:
			return ""
		}
	})
	if err != nil {
		t.Fatalf("loadReducerQueueConfig() error = %v, want nil", err)
	}

	if got, want := cfg.RetryDelay, 2*time.Minute; got != want {
		t.Fatalf("retryDelay = %v, want %v", got, want)
	}
	if got, want := cfg.MaxAttempts, 5; got != want {
		t.Fatalf("maxAttempts = %d, want %d", got, want)
	}
}

func TestLoadReducerWorkerCount_EnvOverride(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(k string) string {
		if k == "PCG_REDUCER_WORKERS" {
			return "6"
		}
		return ""
	})
	if got != 6 {
		t.Fatalf("got %d, want 6", got)
	}
}

func TestLoadReducerWorkerCount_DefaultCap(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(string) string { return "" })
	if got < 1 || got > 4 {
		t.Fatalf("got %d, want 1-4", got)
	}
}

func TestLoadReducerWorkerCount_InvalidEnv(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(k string) string {
		if k == "PCG_REDUCER_WORKERS" {
			return "not-a-number"
		}
		return ""
	})
	if got < 1 || got > 4 {
		t.Fatalf("got %d, want 1-4 (fallback)", got)
	}
}

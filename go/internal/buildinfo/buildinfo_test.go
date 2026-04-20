package buildinfo

import "testing"

func TestAppVersionDefaultsToDevWhenEmpty(t *testing.T) {
	t.Parallel()

	original := Version
	Version = "   "
	t.Cleanup(func() { Version = original })

	if got, want := AppVersion(), "dev"; got != want {
		t.Fatalf("AppVersion() = %q, want %q", got, want)
	}
}

func TestAppVersionPreservesInjectedValue(t *testing.T) {
	t.Parallel()

	original := Version
	Version = "v0.1.0"
	t.Cleanup(func() { Version = original })

	if got, want := AppVersion(), "v0.1.0"; got != want {
		t.Fatalf("AppVersion() = %q, want %q", got, want)
	}
}

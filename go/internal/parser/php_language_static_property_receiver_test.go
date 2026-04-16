package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathPHPInfersStaticPropertyReceiverChains(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "static_property_receiver.php")
	writeTestFile(
		t,
		filePath,
		`<?php
class Service {
    public function info(string $message): void {}
}

class Registry {
    private static Service $service;

    public static function boot(): void {
        self::$service->info('ready');
    }
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	call := assertBucketItemByFieldValue(t, got, "function_calls", "full_name", "self::$service.info")
	phpAssertStringFieldValue(t, call, "inferred_obj_type", "Service")
}

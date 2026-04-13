package parser

import (
	"os"
	"path/filepath"
)

func ensureParentDirectory(path string) error {
	return os.MkdirAll(filepath.Dir(path), 0o755)
}

func osWriteFile(path string, body []byte) error {
	return os.WriteFile(path, body, 0o644)
}

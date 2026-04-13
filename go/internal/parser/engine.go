package parser

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
)

// Engine owns native parser dispatch.
type Engine struct {
	registry Registry
	runtime  *Runtime
}

// DefaultEngine constructs the native parser engine for the built-in registry.
func DefaultEngine() (*Engine, error) {
	return NewEngine(DefaultRegistry(), NewRuntime())
}

// NewEngine constructs one parser engine instance.
func NewEngine(registry Registry, runtime *Runtime) (*Engine, error) {
	if runtime == nil {
		return nil, fmt.Errorf("parser runtime is required")
	}
	return &Engine{
		registry: registry,
		runtime:  runtime,
	}, nil
}

// ParsePath parses one file through the built-in engine contract.
func (e *Engine) ParsePath(
	repoRoot string,
	path string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	resolvedRepoRoot, err := filepath.Abs(repoRoot)
	if err != nil {
		return nil, fmt.Errorf("resolve repo root %q: %w", repoRoot, err)
	}
	resolvedPath, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("resolve path %q: %w", path, err)
	}

	definition, ok := e.registry.LookupByPath(resolvedPath)
	if !ok {
		return nil, fmt.Errorf("no parser registered for %q", resolvedPath)
	}

	payload, err := e.parseDefinition(definition, resolvedPath, isDependency, options)
	if err != nil {
		return nil, err
	}
	payload["repo_path"] = resolvedRepoRoot
	return payload, nil
}

// PreScanPaths returns the import-map contract used by the collector prescan path.
func (e *Engine) PreScanPaths(paths []string) (map[string][]string, error) {
	results := make(map[string][]string)
	for _, rawPath := range paths {
		resolvedPath, err := filepath.Abs(rawPath)
		if err != nil {
			return nil, fmt.Errorf("resolve prescan path %q: %w", rawPath, err)
		}

		definition, ok := e.registry.LookupByPath(resolvedPath)
		if !ok {
			continue
		}

		var names []string
		switch definition.Language {
		case "c":
			names, err = e.preScanC(resolvedPath)
		case "c_sharp":
			names, err = e.preScanCSharp(resolvedPath)
		case "cpp":
			names, err = e.preScanCPP(resolvedPath)
		case "dart":
			names, err = e.preScanDart(resolvedPath)
		case "elixir":
			names, err = e.preScanElixir(resolvedPath)
		case "haskell":
			names, err = e.preScanHaskell(resolvedPath)
		case "javascript":
			names, err = e.preScanJavaScriptLike(resolvedPath, "javascript", "javascript")
		case "java":
			names, err = e.preScanJava(resolvedPath)
		case "kotlin":
			names, err = e.preScanKotlin(resolvedPath)
		case "perl":
			names, err = e.preScanPerl(resolvedPath)
		case "php":
			names, err = e.preScanPHP(resolvedPath)
		case "python":
			names, err = e.preScanPython(resolvedPath)
		case "ruby":
			names, err = e.preScanRuby(resolvedPath)
		case "go":
			names, err = e.preScanGo(resolvedPath)
		case "groovy":
			names, err = e.preScanGroovy(resolvedPath)
		case "rust":
			names, err = e.preScanRust(resolvedPath)
		case "scala":
			names, err = e.preScanScala(resolvedPath)
		case "swift":
			names, err = e.preScanSwift(resolvedPath)
		case "tsx":
			names, err = e.preScanJavaScriptLike(resolvedPath, "tsx", "tsx")
		case "typescript":
			names, err = e.preScanJavaScriptLike(resolvedPath, "typescript", "typescript")
		default:
			continue
		}
		if err != nil {
			return nil, err
		}
		for _, name := range names {
			results[name] = append(results[name], resolvedPath)
		}
	}

	for _, paths := range results {
		slices.Sort(paths)
	}
	return results, nil
}

func (e *Engine) parseDefinition(
	definition Definition,
	resolvedPath string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	switch definition.Language {
	case "c":
		return e.parseC(resolvedPath, isDependency, options)
	case "c_sharp":
		return e.parseCSharp(resolvedPath, isDependency, options)
	case "cpp":
		return e.parseCPP(resolvedPath, isDependency, options)
	case "dart":
		return e.parseDart(resolvedPath, isDependency, options)
	case "dockerfile":
		return e.parseDockerfile(resolvedPath, isDependency, options)
	case "elixir":
		return e.parseElixir(resolvedPath, isDependency, options)
	case "haskell":
		return e.parseHaskell(resolvedPath, isDependency, options)
	case "javascript":
		return e.parseJavaScriptLike(resolvedPath, "javascript", "javascript", isDependency, options)
	case "json":
		return e.parseJSON(resolvedPath, isDependency, options)
	case "java":
		return e.parseJava(resolvedPath, isDependency, options)
	case "kotlin":
		return e.parseKotlin(resolvedPath, isDependency, options)
	case "perl":
		return e.parsePerl(resolvedPath, isDependency, options)
	case "php":
		return e.parsePHP(resolvedPath, isDependency, options)
	case "python":
		return e.parsePython(resolvedPath, isDependency, options)
	case "ruby":
		return e.parseRuby(resolvedPath, isDependency, options)
	case "rust":
		return e.parseRust(resolvedPath, isDependency, options)
	case "go":
		return e.parseGo(resolvedPath, isDependency, options)
	case "hcl":
		return e.parseHCL(resolvedPath, isDependency, options)
	case "groovy":
		return e.parseGroovy(resolvedPath, isDependency, options)
	case "scala":
		return e.parseScala(resolvedPath, isDependency, options)
	case "sql":
		return e.parseSQL(resolvedPath, isDependency, options)
	case "swift":
		return e.parseSwift(resolvedPath, isDependency, options)
	case "tsx":
		return e.parseJavaScriptLike(resolvedPath, "tsx", "tsx", isDependency, options)
	case "typescript":
		return e.parseJavaScriptLike(resolvedPath, "typescript", "typescript", isDependency, options)
	case "raw_text":
		return parseRawText(resolvedPath, isDependency), nil
	case "yaml":
		return e.parseYAML(resolvedPath, isDependency, options)
	default:
		return nil, fmt.Errorf(
			"parser %q for language %q is not implemented in the native engine yet",
			definition.ParserKey,
			definition.Language,
		)
	}
}

func readSource(path string) ([]byte, error) {
	body, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read source %q: %w", path, err)
	}
	return body, nil
}

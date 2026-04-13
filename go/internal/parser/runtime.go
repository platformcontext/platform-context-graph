package parser

import (
	"fmt"
	"strings"
	"sync"
	"unsafe"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
	tree_sitter_go "github.com/tree-sitter/tree-sitter-go/bindings/go"
	tree_sitter_python "github.com/tree-sitter/tree-sitter-python/bindings/go"
)

type languageLoader func() unsafe.Pointer

// Runtime owns cached tree-sitter language handles.
type Runtime struct {
	mu        sync.Mutex
	languages map[string]*tree_sitter.Language
}

// NewRuntime constructs one native tree-sitter runtime.
func NewRuntime() *Runtime {
	return &Runtime{
		languages: make(map[string]*tree_sitter.Language),
	}
}

// Language returns one cached language handle by canonical or alias name.
func (r *Runtime) Language(name string) (*tree_sitter.Language, error) {
	canonical, err := normalizeLanguageName(name)
	if err != nil {
		return nil, err
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if language := r.languages[canonical]; language != nil {
		return language, nil
	}

	loader, ok := builtinLanguageLoaders[canonical]
	if !ok {
		return nil, fmt.Errorf("parser language %q is not wired into the Go runtime", canonical)
	}

	language := tree_sitter.NewLanguage(loader())
	r.languages[canonical] = language
	return language, nil
}

// Parser returns a new parser configured for one language.
func (r *Runtime) Parser(name string) (*tree_sitter.Parser, error) {
	language, err := r.Language(name)
	if err != nil {
		return nil, err
	}

	parser := tree_sitter.NewParser()
	if err := parser.SetLanguage(language); err != nil {
		parser.Close()
		return nil, fmt.Errorf("set parser language %q: %w", name, err)
	}
	return parser, nil
}

var builtinLanguageLoaders = map[string]languageLoader{
	"go":     tree_sitter_go.Language,
	"python": tree_sitter_python.Language,
}

func normalizeLanguageName(name string) (string, error) {
	switch strings.TrimSpace(strings.ToLower(name)) {
	case "go":
		return "go", nil
	case "py", "python":
		return "python", nil
	default:
		return "", fmt.Errorf("unsupported language %q", name)
	}
}

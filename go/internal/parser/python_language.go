package parser

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
)

func (e *Engine) parsePython(
	path string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	parser, err := e.runtime.Parser("python")
	if err != nil {
		return nil, err
	}
	defer parser.Close()

	source, err := readSource(path)
	if err != nil {
		return nil, err
	}
	if strings.EqualFold(filepath.Ext(path), ".ipynb") {
		tempPythonPath, err := convertNotebookToTempPython(path, source)
		if err != nil {
			return nil, err
		}
		defer func() {
			_ = os.Remove(tempPythonPath)
		}()
		source, err = readSource(tempPythonPath)
		if err != nil {
			return nil, err
		}
	}
	tree := parser.Parse(source, nil)
	if tree == nil {
		return nil, fmt.Errorf("parse python file %q: parser returned nil tree", path)
	}
	defer tree.Close()

	payload := basePayload(path, "python", isDependency)
	root := tree.RootNode()
	scope := options.normalizedVariableScope()

	walkNamed(root, func(node *tree_sitter.Node) {
		switch node.Kind() {
		case "class_definition":
			nameNode := node.ChildByFieldName("name")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"lang":        "python",
			})
		case "function_definition":
			nameNode := node.ChildByFieldName("name")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			item := map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"decorators":  []string{},
				"lang":        "python",
			}
			if options.IndexSource {
				item["source"] = nodeText(node, source)
			}
			appendBucket(payload, "functions", item)
		case "assignment":
			if scope == "module" && !pythonModuleScoped(node) {
				return
			}
			left := node.ChildByFieldName("left")
			if left == nil || left.Kind() != "identifier" {
				return
			}
			name := nodeText(left, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			item := map[string]any{
				"name":        name,
				"line_number": nodeLine(left),
				"end_line":    nodeEndLine(node),
				"lang":        "python",
			}
			if options.IndexSource {
				item["source"] = nodeText(node, source)
			}
			appendBucket(payload, "variables", item)
		case "import_statement":
			cursor := node.Walk()
			defer cursor.Close()
			for _, child := range node.NamedChildren(cursor) {
				child := child
				if child.Kind() != "dotted_name" && child.Kind() != "aliased_import" && child.Kind() != "identifier" {
					continue
				}
				name := pythonImportName(&child, source)
				if strings.TrimSpace(name) == "" {
					continue
				}
				appendBucket(payload, "imports", map[string]any{
					"name":        name,
					"line_number": nodeLine(&child),
					"lang":        "python",
				})
			}
		case "call":
			function := node.ChildByFieldName("function")
			name := pythonCallName(function, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "function_calls", map[string]any{
				"name":        name,
				"line_number": nodeLine(node),
				"lang":        "python",
			})
		}
	})

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")
	payload["framework_semantics"] = buildPythonFrameworkSemantics(string(source))
	payload["orm_table_mappings"] = buildPythonORMTableMappings(string(source))

	return payload, nil
}

func (e *Engine) preScanPython(path string) ([]string, error) {
	payload, err := e.parsePython(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes")
	slices.Sort(names)
	return names, nil
}

func pythonImportName(node *tree_sitter.Node, source []byte) string {
	if node == nil {
		return ""
	}
	if node.Kind() == "aliased_import" {
		nameNode := node.ChildByFieldName("name")
		return nodeText(nameNode, source)
	}
	return nodeText(node, source)
}

func pythonCallName(node *tree_sitter.Node, source []byte) string {
	if node == nil {
		return ""
	}
	switch node.Kind() {
	case "identifier":
		return nodeText(node, source)
	case "attribute":
		attribute := node.ChildByFieldName("attribute")
		return nodeText(attribute, source)
	default:
		return ""
	}
}

func pythonModuleScoped(node *tree_sitter.Node) bool {
	for current := node.Parent(); current != nil; current = current.Parent() {
		switch current.Kind() {
		case "function_definition", "lambda":
			return false
		case "module", "class_definition":
			return true
		}
	}
	return true
}

func convertNotebookToTempPython(path string, source []byte) (string, error) {
	code, err := pythonNotebookSource(source)
	if err != nil {
		return "", fmt.Errorf("convert notebook %q: %w", path, err)
	}

	tempFile, err := os.CreateTemp("", "pcg-notebook-*.py")
	if err != nil {
		return "", fmt.Errorf("create temporary python file for %q: %w", path, err)
	}
	defer tempFile.Close()

	if _, err := tempFile.WriteString(code); err != nil {
		_ = os.Remove(tempFile.Name())
		return "", fmt.Errorf("write temporary python file for %q: %w", path, err)
	}
	return tempFile.Name(), nil
}

func pythonNotebookSource(source []byte) (string, error) {
	var notebook map[string]any
	if err := json.Unmarshal(source, &notebook); err != nil {
		return "", fmt.Errorf("decode notebook json: %w", err)
	}

	cells, _ := notebook["cells"].([]any)
	if len(cells) == 0 {
		return "", nil
	}

	codeCells := make([]string, 0, len(cells))
	for _, rawCell := range cells {
		cell, ok := rawCell.(map[string]any)
		if !ok {
			continue
		}
		if !strings.EqualFold(fmt.Sprint(cell["cell_type"]), "code") {
			continue
		}
		cellSource := notebookCellSource(cell["source"])
		if strings.TrimSpace(cellSource) == "" {
			continue
		}
		codeCells = append(codeCells, cellSource)
	}
	return strings.Join(codeCells, "\n\n"), nil
}

func notebookCellSource(raw any) string {
	switch typed := raw.(type) {
	case string:
		return typed
	case []any:
		parts := make([]string, 0, len(typed))
		for _, item := range typed {
			parts = append(parts, fmt.Sprint(item))
		}
		return strings.Join(parts, "")
	case []string:
		return strings.Join(typed, "")
	default:
		return fmt.Sprint(raw)
	}
}

func sortNamedBucket(payload map[string]any, key string) {
	items, _ := payload[key].([]map[string]any)
	slices.SortFunc(items, func(left, right map[string]any) int {
		leftLine, _ := left["line_number"].(int)
		rightLine, _ := right["line_number"].(int)
		if leftLine != rightLine {
			return leftLine - rightLine
		}
		leftName, _ := left["name"].(string)
		rightName, _ := right["name"].(string)
		return strings.Compare(leftName, rightName)
	})
	payload[key] = items
}

func collectBucketNames(payload map[string]any, keys ...string) []string {
	var names []string
	for _, key := range keys {
		items, _ := payload[key].([]map[string]any)
		for _, item := range items {
			name, _ := item["name"].(string)
			if strings.TrimSpace(name) != "" {
				names = append(names, filepath.Clean(name))
			}
		}
	}
	return names
}

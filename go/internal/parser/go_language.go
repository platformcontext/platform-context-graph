package parser

import (
	"fmt"
	"slices"
	"strconv"
	"strings"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
)

func (e *Engine) parseGo(
	path string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	parser, err := e.runtime.Parser("go")
	if err != nil {
		return nil, err
	}
	defer parser.Close()

	source, err := readSource(path)
	if err != nil {
		return nil, err
	}
	tree := parser.Parse(source, nil)
	if tree == nil {
		return nil, fmt.Errorf("parse go file %q: parser returned nil tree", path)
	}
	defer tree.Close()

	payload := basePayload(path, "go", isDependency)
	payload["interfaces"] = []map[string]any{}
	payload["structs"] = []map[string]any{}
	payload["embedded_sql_queries"] = extractGoEmbeddedSQLQueries(string(source))
	scope := options.normalizedVariableScope()
	root := tree.RootNode()

	walkNamed(root, func(node *tree_sitter.Node) {
		switch node.Kind() {
		case "function_declaration", "method_declaration":
			nameNode := node.ChildByFieldName("name")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			item := map[string]any{
				"name":                  name,
				"line_number":           nodeLine(nameNode),
				"end_line":              nodeEndLine(node),
				"decorators":            []string{},
				"lang":                  "go",
				"cyclomatic_complexity": cyclomaticComplexity(node),
			}
			if docstring := goDocstring(node, source); docstring != "" {
				item["docstring"] = docstring
			}
			if classContext := goReceiverContext(node, source); classContext != "" {
				item["class_context"] = classContext
			}
			if options.IndexSource {
				item["source"] = nodeText(node, source)
			}
			appendBucket(payload, "functions", item)
		case "type_spec":
			nameNode := node.ChildByFieldName("name")
			typeNode := node.ChildByFieldName("type")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" || typeNode == nil {
				return
			}
			item := map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"lang":        "go",
			}
			if docstring := goDocstring(node, source); docstring != "" {
				item["docstring"] = docstring
			}
			switch typeNode.Kind() {
			case "struct_type":
				appendBucket(payload, "structs", item)
			case "interface_type":
				appendBucket(payload, "interfaces", item)
			}
		case "import_spec":
			pathNode := node.ChildByFieldName("path")
			if pathNode == nil {
				return
			}
			name := strings.Trim(nodeText(pathNode, source), `"`)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "imports", map[string]any{
				"name":        name,
				"line_number": nodeLine(pathNode),
				"lang":        "go",
			})
		case "call_expression":
			functionNode := node.ChildByFieldName("function")
			name := goCallName(functionNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "function_calls", map[string]any{
				"name":        name,
				"line_number": nodeLine(node),
				"lang":        "go",
			})
		case "var_spec", "const_spec":
			if scope == "module" && goInsideFunction(node) {
				return
			}
			for _, item := range goVariableNames(node, source) {
				appendBucket(payload, "variables", item)
			}
		case "short_var_declaration":
			if scope == "module" {
				return
			}
			for _, item := range goShortVariableNames(node, source) {
				appendBucket(payload, "variables", item)
			}
		}
	})

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "structs")
	sortNamedBucket(payload, "interfaces")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")

	return payload, nil
}

func (e *Engine) preScanGo(path string) ([]string, error) {
	payload, err := e.parseGo(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "structs", "interfaces")
	slices.Sort(names)
	return names, nil
}

func goCallName(node *tree_sitter.Node, source []byte) string {
	if node == nil {
		return ""
	}
	switch node.Kind() {
	case "identifier":
		return nodeText(node, source)
	case "selector_expression":
		field := node.ChildByFieldName("field")
		return nodeText(field, source)
	default:
		return ""
	}
}

func goInsideFunction(node *tree_sitter.Node) bool {
	for current := node.Parent(); current != nil; current = current.Parent() {
		switch current.Kind() {
		case "function_declaration", "method_declaration", "func_literal":
			return true
		}
	}
	return false
}

func goVariableNames(node *tree_sitter.Node, source []byte) []map[string]any {
	nameNode := node.ChildByFieldName("name")
	if nameNode == nil {
		return nil
	}
	return []map[string]any{{
		"name":        nodeText(nameNode, source),
		"line_number": nodeLine(nameNode),
		"end_line":    nodeEndLine(node),
		"lang":        "go",
	}}
}

func goShortVariableNames(node *tree_sitter.Node, source []byte) []map[string]any {
	left := node.ChildByFieldName("left")
	if left == nil {
		return nil
	}

	var items []map[string]any
	cursor := left.Walk()
	defer cursor.Close()
	for _, child := range left.NamedChildren(cursor) {
		child := child
		if child.Kind() != "identifier" {
			continue
		}
		items = append(items, map[string]any{
			"name":        nodeText(&child, source),
			"line_number": nodeLine(&child),
			"end_line":    nodeEndLine(node),
			"lang":        "go",
		})
	}
	return items
}

func lineNumberLess(left, right map[string]any) int {
	leftLine, _ := left["line_number"].(int)
	rightLine, _ := right["line_number"].(int)
	if leftLine != rightLine {
		return leftLine - rightLine
	}
	leftName := fmt.Sprint(left["name"])
	rightName := fmt.Sprint(right["name"])
	return strings.Compare(leftName, rightName)
}

func intValue(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case uint:
		return int(typed)
	case uint32:
		return int(typed)
	case uint64:
		return int(typed)
	case string:
		parsed, _ := strconv.Atoi(typed)
		return parsed
	default:
		return 0
	}
}

func goDocstring(node *tree_sitter.Node, source []byte) string {
	if node == nil {
		return ""
	}

	lines := strings.Split(string(source), "\n")
	startLine := nodeLine(node) - 2
	if startLine < 0 || startLine >= len(lines) {
		return ""
	}

	comments := make([]string, 0)
	for index := startLine; index >= 0; index-- {
		trimmed := strings.TrimSpace(lines[index])
		if trimmed == "" {
			if len(comments) == 0 {
				return ""
			}
			break
		}
		if strings.HasPrefix(trimmed, "//") {
			comments = append([]string{strings.TrimSpace(strings.TrimPrefix(trimmed, "//"))}, comments...)
			continue
		}
		if strings.HasPrefix(trimmed, "/*") && strings.HasSuffix(trimmed, "*/") {
			comments = append([]string{strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(trimmed, "/*"), "*/"))}, comments...)
			continue
		}
		break
	}

	return strings.TrimSpace(strings.Join(comments, "\n"))
}

func goReceiverContext(node *tree_sitter.Node, source []byte) string {
	if node == nil {
		return ""
	}

	receiver := node.ChildByFieldName("receiver")
	if receiver == nil {
		return ""
	}

	typeNode := firstNamedDescendant(receiver,
		"type_identifier",
		"qualified_type",
		"generic_type",
		"pointer_type",
		"array_type",
		"slice_type",
	)
	if typeNode == nil {
		return ""
	}

	value := strings.TrimSpace(nodeText(typeNode, source))
	value = strings.TrimSpace(strings.TrimPrefix(value, "*"))
	value = strings.Trim(value, "[]")
	if index := strings.LastIndex(value, "."); index >= 0 {
		value = value[index+1:]
	}
	return strings.TrimSpace(value)
}

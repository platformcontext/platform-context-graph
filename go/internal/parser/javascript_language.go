package parser

import (
	"fmt"
	"slices"
	"strings"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
)

func (e *Engine) parseJavaScriptLike(
	path string,
	runtimeLanguage string,
	outputLanguage string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	parser, err := e.runtime.Parser(runtimeLanguage)
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
		return nil, fmt.Errorf("parse %s file %q: parser returned nil tree", outputLanguage, path)
	}
	defer tree.Close()

	payload := basePayload(path, outputLanguage, isDependency)
	if outputLanguage != "javascript" {
		payload["interfaces"] = []map[string]any{}
	}
	scope := options.normalizedVariableScope()
	root := tree.RootNode()

	walkNamed(root, func(node *tree_sitter.Node) {
		switch node.Kind() {
		case "function_declaration":
			nameNode := node.ChildByFieldName("name")
			appendFunctionDeclaration(payload, node, nameNode, source, outputLanguage, options)
		case "method_definition", "method_signature":
			nameNode := node.ChildByFieldName("name")
			appendFunctionDeclaration(payload, node, nameNode, source, outputLanguage, options)
		case "class_declaration", "abstract_class_declaration":
			nameNode := node.ChildByFieldName("name")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"lang":        outputLanguage,
			})
		case "interface_declaration":
			if outputLanguage == "javascript" {
				return
			}
			nameNode := node.ChildByFieldName("name")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "interfaces", map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"lang":        outputLanguage,
			})
		case "variable_declarator":
			nameNode := node.ChildByFieldName("name")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			valueNode := node.ChildByFieldName("value")
			if isJavaScriptFunctionValue(valueNode) {
				appendFunctionDeclaration(payload, node, nameNode, source, outputLanguage, options)
				return
			}
			if scope == "module" && javaScriptInsideFunction(node) {
				return
			}
			appendBucket(payload, "variables", map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"lang":        outputLanguage,
			})
		case "import_statement":
			for _, item := range javaScriptImportEntries(node, source, outputLanguage) {
				appendBucket(payload, "imports", item)
			}
		case "call_expression":
			functionNode := node.ChildByFieldName("function")
			name := javaScriptCallName(functionNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "function_calls", map[string]any{
				"name":        name,
				"line_number": nodeLine(node),
				"lang":        outputLanguage,
			})
		}
	})

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")
	if outputLanguage != "javascript" {
		sortNamedBucket(payload, "interfaces")
	}
	payload["framework_semantics"] = map[string]any{"frameworks": []string{}}

	return payload, nil
}

func (e *Engine) preScanJavaScriptLike(
	path string,
	runtimeLanguage string,
	outputLanguage string,
) ([]string, error) {
	payload, err := e.parseJavaScriptLike(path, runtimeLanguage, outputLanguage, false, Options{})
	if err != nil {
		return nil, err
	}
	keys := []string{"functions", "classes"}
	if outputLanguage != "javascript" {
		keys = append(keys, "interfaces")
	}
	names := collectBucketNames(payload, keys...)
	slices.Sort(names)
	return names, nil
}

func appendFunctionDeclaration(
	payload map[string]any,
	node *tree_sitter.Node,
	nameNode *tree_sitter.Node,
	source []byte,
	lang string,
	options Options,
) {
	name := nodeText(nameNode, source)
	if strings.TrimSpace(name) == "" {
		return
	}

	item := map[string]any{
		"name":        name,
		"line_number": nodeLine(nameNode),
		"end_line":    nodeEndLine(node),
		"decorators":  []string{},
		"lang":        lang,
	}
	if options.IndexSource {
		item["source"] = nodeText(node, source)
	}
	appendBucket(payload, "functions", item)
}

func isJavaScriptFunctionValue(node *tree_sitter.Node) bool {
	if node == nil {
		return false
	}
	switch node.Kind() {
	case "function_expression", "arrow_function", "generator_function", "generator_function_declaration":
		return true
	default:
		return false
	}
}

func javaScriptInsideFunction(node *tree_sitter.Node) bool {
	for current := node.Parent(); current != nil; current = current.Parent() {
		switch current.Kind() {
		case "function_declaration", "function_expression", "arrow_function", "method_definition":
			return true
		}
	}
	return false
}

func javaScriptImportEntries(node *tree_sitter.Node, source []byte, lang string) []map[string]any {
	sourceNode := node.ChildByFieldName("source")
	moduleSource := strings.Trim(nodeText(sourceNode, source), `"'`)
	if strings.TrimSpace(moduleSource) == "" {
		return nil
	}

	importNode := node.ChildByFieldName("import")
	if importNode == nil {
		cursor := node.Walk()
		defer cursor.Close()
		for _, child := range node.NamedChildren(cursor) {
			child := child
			if child.Kind() == "string" {
				continue
			}
			importNode = &child
			break
		}
	}
	if importNode == nil {
		return []map[string]any{{
			"name":        moduleSource,
			"source":      moduleSource,
			"line_number": nodeLine(sourceNode),
			"lang":        lang,
		}}
	}

	items := make([]map[string]any, 0)
	cursor := importNode.Walk()
	defer cursor.Close()
	children := importNode.NamedChildren(cursor)
	if len(children) == 0 {
		children = []tree_sitter.Node{*importNode}
	}
	for _, child := range children {
		child := child
		switch child.Kind() {
		case "import_clause":
			clauseCursor := child.Walk()
			defer clauseCursor.Close()
			for _, clauseChild := range child.NamedChildren(clauseCursor) {
				clauseChild := clauseChild
				items = append(items, javaScriptImportEntriesFromClause(&clauseChild, moduleSource, source, lang)...)
			}
		case "identifier":
			items = append(items, javaScriptImportEntriesFromClause(&child, moduleSource, source, lang)...)
		case "namespace_import", "named_imports":
			items = append(items, javaScriptImportEntriesFromClause(&child, moduleSource, source, lang)...)
		}
	}
	if len(items) == 0 {
		items = append(items, map[string]any{
			"name":        moduleSource,
			"source":      moduleSource,
			"line_number": nodeLine(sourceNode),
			"lang":        lang,
		})
	}
	return items
}

func javaScriptImportEntriesFromClause(
	node *tree_sitter.Node,
	moduleSource string,
	source []byte,
	lang string,
) []map[string]any {
	if node == nil {
		return nil
	}

	switch node.Kind() {
	case "identifier":
		return []map[string]any{{
			"name":        "default",
			"source":      moduleSource,
			"alias":       nodeText(node, source),
			"line_number": nodeLine(node),
			"lang":        lang,
		}}
	case "namespace_import":
		aliasNode := node.ChildByFieldName("name")
		return []map[string]any{{
			"name":        "*",
			"source":      moduleSource,
			"alias":       nodeText(aliasNode, source),
			"line_number": nodeLine(node),
			"lang":        lang,
		}}
	case "named_imports":
		items := make([]map[string]any, 0)
		cursor := node.Walk()
		defer cursor.Close()
		for _, specifier := range node.NamedChildren(cursor) {
			specifier := specifier
			if specifier.Kind() != "import_specifier" {
				continue
			}
			nameNode := specifier.ChildByFieldName("name")
			aliasNode := specifier.ChildByFieldName("alias")
			items = append(items, map[string]any{
				"name":        nodeText(nameNode, source),
				"source":      moduleSource,
				"alias":       nodeText(aliasNode, source),
				"line_number": nodeLine(&specifier),
				"lang":        lang,
			})
		}
		return items
	default:
		return nil
	}
}

func javaScriptCallName(node *tree_sitter.Node, source []byte) string {
	if node == nil {
		return ""
	}
	switch node.Kind() {
	case "identifier":
		return nodeText(node, source)
	case "member_expression":
		property := node.ChildByFieldName("property")
		return nodeText(property, source)
	default:
		return ""
	}
}

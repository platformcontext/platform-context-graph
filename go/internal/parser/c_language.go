package parser

import (
	"fmt"
	"slices"
	"strings"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
)

func (e *Engine) parseC(
	path string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	parser, err := e.runtime.Parser("c")
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
		return nil, fmt.Errorf("parse c file %q: parser returned nil tree", path)
	}
	defer tree.Close()

	payload := basePayload(path, "c", isDependency)
	payload["structs"] = []map[string]any{}
	payload["enums"] = []map[string]any{}
	payload["unions"] = []map[string]any{}
	payload["macros"] = []map[string]any{}
	root := tree.RootNode()
	scope := options.normalizedVariableScope()

	walkNamed(root, func(node *tree_sitter.Node) {
		switch node.Kind() {
		case "preproc_include":
			appendImportFromNode(payload, firstNamedDescendant(node, "system_lib_string", "string_literal"), source, "c")
		case "preproc_def", "preproc_function_def":
			appendMacro(payload, node, source, "c")
		case "struct_specifier":
			appendNamedType(payload, "structs", node, source, "c")
		case "enum_specifier":
			appendNamedType(payload, "enums", node, source, "c")
		case "union_specifier":
			appendNamedType(payload, "unions", node, source, "c")
		case "function_definition":
			appendCFunction(payload, node, source, options)
		case "declaration":
			if strings.HasPrefix(strings.TrimSpace(nodeText(node, source)), "typedef ") {
				return
			}
			if scope == "module" && cLikeInsideFunction(node) {
				return
			}
			appendCDeclarationVariables(payload, node, source, "c")
		case "call_expression":
			appendCall(payload, cLikeCallNameNode(node.ChildByFieldName("function")), source, "c")
		}
	})

	sortSystemsPayload(
		payload,
		"functions",
		"structs",
		"enums",
		"unions",
		"variables",
		"imports",
		"function_calls",
		"macros",
	)
	payload["framework_semantics"] = map[string]any{"frameworks": []string{}}

	return payload, nil
}

func (e *Engine) preScanC(path string) ([]string, error) {
	payload, err := e.parseC(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "structs", "enums", "unions", "macros")
	slices.Sort(names)
	return names, nil
}

func appendCFunction(payload map[string]any, node *tree_sitter.Node, source []byte, options Options) {
	nameNode := firstNamedDescendant(node, "identifier", "field_identifier")
	name := nodeText(nameNode, source)
	if strings.TrimSpace(name) == "" {
		return
	}
	item := map[string]any{
		"name":        name,
		"line_number": nodeLine(nameNode),
		"end_line":    nodeEndLine(node),
		"decorators":  []string{},
		"lang":        "c",
	}
	if options.IndexSource {
		item["source"] = nodeText(node, source)
	}
	appendBucket(payload, "functions", item)
}

func appendCDeclarationVariables(payload map[string]any, node *tree_sitter.Node, source []byte, lang string) {
	walkNamed(node, func(child *tree_sitter.Node) {
		if child.Kind() != "init_declarator" {
			return
		}
		nameNode := firstNamedDescendant(child, "identifier")
		name := nodeText(nameNode, source)
		if strings.TrimSpace(name) == "" {
			return
		}
		appendBucket(payload, "variables", map[string]any{
			"name":        name,
			"line_number": nodeLine(nameNode),
			"end_line":    nodeEndLine(node),
			"lang":        lang,
		})
	})
}

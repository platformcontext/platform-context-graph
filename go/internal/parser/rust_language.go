package parser

import (
	"fmt"
	"slices"
	"strings"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
)

func (e *Engine) parseRust(
	path string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	parser, err := e.runtime.Parser("rust")
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
		return nil, fmt.Errorf("parse rust file %q: parser returned nil tree", path)
	}
	defer tree.Close()

	payload := basePayload(path, "rust", isDependency)
	payload["traits"] = []map[string]any{}
	root := tree.RootNode()

	walkNamed(root, func(node *tree_sitter.Node) {
		switch node.Kind() {
		case "function_item", "function_signature_item":
			appendRustFunction(payload, node, source, options)
		case "struct_item", "enum_item", "union_item":
			nameNode := firstNamedDescendant(node, "type_identifier")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"lang":        "rust",
			})
		case "trait_item":
			nameNode := firstNamedDescendant(node, "type_identifier")
			name := nodeText(nameNode, source)
			if strings.TrimSpace(name) == "" {
				return
			}
			appendBucket(payload, "traits", map[string]any{
				"name":        name,
				"line_number": nodeLine(nameNode),
				"end_line":    nodeEndLine(node),
				"lang":        "rust",
			})
		case "use_declaration":
			name := strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(nodeText(node, source), "use "), ";"))
			if name == "" {
				return
			}
			appendBucket(payload, "imports", map[string]any{
				"name":        name,
				"line_number": nodeLine(node),
				"lang":        "rust",
			})
		case "call_expression":
			appendCall(payload, rustCallNameNode(node), source, "rust")
		case "macro_invocation":
			appendCall(payload, firstNamedDescendant(node, "identifier"), source, "rust")
		}
	})

	sortSystemsPayload(payload, "functions", "classes", "traits", "imports", "function_calls")
	payload["framework_semantics"] = map[string]any{"frameworks": []string{}}

	return payload, nil
}

func (e *Engine) preScanRust(path string) ([]string, error) {
	payload, err := e.parseRust(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes", "traits")
	slices.Sort(names)
	return names, nil
}

func appendRustFunction(payload map[string]any, node *tree_sitter.Node, source []byte, options Options) {
	nameNode := firstNamedDescendant(node, "identifier")
	name := nodeText(nameNode, source)
	if strings.TrimSpace(name) == "" {
		return
	}

	item := map[string]any{
		"name":        name,
		"line_number": nodeLine(nameNode),
		"end_line":    nodeEndLine(node),
		"decorators":  []string{},
		"lang":        "rust",
	}
	if classContext := nearestNamedAncestor(node, source, "impl_item", "trait_item"); classContext != "" {
		item["class_context"] = classContext
	}
	if options.IndexSource {
		item["source"] = nodeText(node, source)
	}
	appendBucket(payload, "functions", item)
}

func rustCallNameNode(node *tree_sitter.Node) *tree_sitter.Node {
	if node == nil {
		return nil
	}
	if functionNode := node.ChildByFieldName("function"); functionNode != nil {
		return firstNamedDescendant(functionNode, "identifier", "field_identifier")
	}
	return firstNamedDescendant(node, "identifier", "field_identifier")
}

func cLikeInsideFunction(node *tree_sitter.Node) bool {
	for current := node.Parent(); current != nil; current = current.Parent() {
		if current.Kind() == "function_definition" {
			return true
		}
	}
	return false
}

func cLikeCallNameNode(node *tree_sitter.Node) *tree_sitter.Node {
	if node == nil {
		return nil
	}
	if node.Kind() == "identifier" || node.Kind() == "field_identifier" {
		return node
	}
	return firstNamedDescendant(node, "identifier", "field_identifier")
}

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
	payload["impl_blocks"] = []map[string]any{}
	payload["traits"] = []map[string]any{}
	root := tree.RootNode()

	walkNamed(root, func(node *tree_sitter.Node) {
		switch node.Kind() {
		case "impl_item":
			appendRustImplBlock(payload, node, source)
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

	sortSystemsPayload(payload, "functions", "classes", "traits", "imports", "function_calls", "impl_blocks")
	payload["framework_semantics"] = map[string]any{"frameworks": []string{}}

	return payload, nil
}

func (e *Engine) preScanRust(path string) ([]string, error) {
	payload, err := e.parseRust(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes", "traits", "impl_blocks")
	slices.Sort(names)
	return names, nil
}

func appendRustImplBlock(payload map[string]any, node *tree_sitter.Node, source []byte) {
	header := strings.TrimSpace(nodeText(node, source))
	if idx := strings.Index(header, "{"); idx >= 0 {
		header = header[:idx]
	}
	header = strings.TrimSpace(strings.TrimPrefix(header, "impl"))
	header = strings.TrimSpace(rustStripTypeParameters(header))

	kind := "inherent_impl"
	traitName := ""
	targetName := header

	if idx := strings.Index(header, " for "); idx >= 0 {
		kind = "trait_impl"
		traitName = strings.TrimSpace(header[:idx])
		targetName = strings.TrimSpace(header[idx+len(" for "):])
	}
	if idx := strings.Index(targetName, " where "); idx >= 0 {
		targetName = strings.TrimSpace(targetName[:idx])
	}

	item := map[string]any{
		"name":        rustBaseTypeName(targetName),
		"target":      targetName,
		"line_number": nodeLine(node),
		"end_line":    nodeEndLine(node),
		"kind":        kind,
		"lang":        "rust",
	}
	if traitName != "" {
		item["trait"] = rustBaseTypeName(traitName)
	}
	appendBucket(payload, "impl_blocks", item)
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
	if implContext := rustImplContext(node, source); implContext != "" {
		item["impl_context"] = implContext
	}
	if options.IndexSource {
		item["source"] = nodeText(node, source)
	}
	appendBucket(payload, "functions", item)
}

func rustImplContext(node *tree_sitter.Node, source []byte) string {
	for current := node.Parent(); current != nil; current = current.Parent() {
		if current.Kind() != "impl_item" {
			continue
		}
		typeNode := current.ChildByFieldName("type")
		implContext := nodeText(typeNode, source)
		implContext = strings.TrimSpace(implContext)
		if implContext == "" {
			return ""
		}
		implContext = strings.TrimSuffix(implContext, ";")
		implContext = strings.TrimSpace(implContext)
		if idx := strings.LastIndex(implContext, "::"); idx >= 0 {
			implContext = implContext[idx+2:]
		}
		if idx := strings.Index(implContext, "<"); idx >= 0 {
			implContext = implContext[:idx]
		}
		return strings.TrimSpace(implContext)
	}
	return ""
}

func rustStripTypeParameters(text string) string {
	trimmed := strings.TrimSpace(text)
	if !strings.HasPrefix(trimmed, "<") {
		return trimmed
	}
	if end := strings.Index(trimmed, ">"); end >= 0 {
		return strings.TrimSpace(trimmed[end+1:])
	}
	return trimmed
}

func rustBaseTypeName(text string) string {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return ""
	}
	if idx := strings.Index(trimmed, "<"); idx >= 0 {
		trimmed = trimmed[:idx]
	}
	if idx := strings.LastIndex(trimmed, "::"); idx >= 0 {
		trimmed = trimmed[idx+2:]
	}
	return strings.TrimSpace(trimmed)
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

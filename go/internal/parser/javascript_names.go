package parser

import (
	"regexp"
	"strings"

	tree_sitter "github.com/tree-sitter/go-tree-sitter"
)

var javaScriptStaticComputedMemberNameRe = regexp.MustCompile(`^(?:[A-Za-z_$][A-Za-z0-9_$]*)(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*$|^(?:0|[1-9][0-9]*)$`)

func javaScriptFunctionName(node *tree_sitter.Node, source []byte) string {
	if node == nil {
		return ""
	}

	switch node.Kind() {
	case "identifier", "property_identifier", "private_property_identifier", "jsx_identifier", "type_identifier":
		return strings.TrimSpace(nodeText(node, source))
	case "computed_property_name":
		return javaScriptComputedPropertyName(node, source)
	default:
		return strings.TrimSpace(nodeText(node, source))
	}
}

func javaScriptComputedPropertyName(node *tree_sitter.Node, source []byte) string {
	text := strings.TrimSpace(nodeText(node, source))
	if text == "" {
		return ""
	}
	if len(text) < 2 || text[0] != '[' || text[len(text)-1] != ']' {
		return text
	}

	inner := strings.TrimSpace(text[1 : len(text)-1])
	if inner == "" {
		return text
	}
	if unquoted, ok := trimJavaScriptQuotes(inner); ok {
		inner = unquoted
	}
	if javaScriptStaticComputedMemberNameRe.MatchString(inner) {
		return inner
	}
	return text
}

func trimJavaScriptQuotes(text string) (string, bool) {
	if len(text) < 2 {
		return text, false
	}

	first := text[0]
	last := text[len(text)-1]
	switch {
	case first == '"' && last == '"':
		return text[1 : len(text)-1], true
	case first == '\'' && last == '\'':
		return text[1 : len(text)-1], true
	case first == '`' && last == '`':
		return text[1 : len(text)-1], true
	default:
		return text, false
	}
}

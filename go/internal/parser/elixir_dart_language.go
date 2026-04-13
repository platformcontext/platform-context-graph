package parser

import (
	"regexp"
	"slices"
	"strings"
)

var (
	elixirModulePattern   = regexp.MustCompile(`^\s*(defmodule|defprotocol|defimpl)\s+(.+)$`)
	elixirFunctionPattern = regexp.MustCompile(`^\s*(def|defp|defmacro|defmacrop|defdelegate|defguard|defguardp)\s+(.+)$`)
	elixirImportPattern   = regexp.MustCompile(`^\s*(use|import|alias|require)\s+(.+)$`)
	elixirAttributePattern = regexp.MustCompile(`^\s*(@[a-z_]\w*)\s+(.+)$`)
	elixirScopedCall      = regexp.MustCompile(`([A-Z][A-Za-z0-9_.]+)\.([a-z_]\w*[!?]?)\(`)
	elixirCallPattern     = regexp.MustCompile(`\b([a-z_]\w*[!?]?)\(`)

	dartImportPattern    = regexp.MustCompile(`^\s*(?:import|export)\s+'([^']+)'`)
	dartClassPattern     = regexp.MustCompile(`^\s*class\s+([A-Za-z_]\w*)`)
	dartMixinPattern     = regexp.MustCompile(`^\s*mixin\s+([A-Za-z_]\w*)`)
	dartEnumPattern      = regexp.MustCompile(`^\s*enum\s+([A-Za-z_]\w*)`)
	dartExtensionPattern = regexp.MustCompile(`^\s*extension\s+([A-Za-z_]\w*)\s+on\b`)
	dartFunctionPattern  = regexp.MustCompile(`^\s*(?:static\s+)?(?:[\w<>\?\[\], ]+\s+)?([A-Za-z_]\w*)\s*\([^)]*\)\s*(?:async\*?|async|=>|\{)`)
	dartVariablePattern  = regexp.MustCompile(`^\s*(?:final|var|const)\s+(?:[\w<>\?\[\], ]+\s+)?([A-Za-z_]\w*)\s*=`)
	dartCallPattern      = regexp.MustCompile(`\b([A-Za-z_]\w*)\s*\(`)
)

func (e *Engine) parseElixir(path string, isDependency bool, options Options) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	payload := basePayload(path, "elixir", isDependency)
	payload["modules"] = []map[string]any{}
	lines := strings.Split(string(source), "\n")
	seenCalls := make(map[string]struct{})
	scopes := make([]elixirScope, 0)
	lastMeaningfulLine := ""

	for index, rawLine := range lines {
		lineNumber := index + 1
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" {
			continue
		}

		if trimmed == "end" {
			var popped elixirScope
			scopes, popped = popElixirScope(scopes)
			if options.IndexSource && popped.item != nil {
				popped.item["end_line"] = lineNumber
				popped.item["source"] = strings.Join(lines[popped.lineNumber-1:lineNumber], "\n")
			}
			lastMeaningfulLine = trimmed
			continue
		}

		if keyword, name, ok := parseElixirModuleLine(trimmed); ok {
			item := map[string]any{
				"name":          name,
				"line_number":   lineNumber,
				"end_line":      lineNumber,
				"lang":          "elixir",
				"is_dependency": isDependency,
				"type":          keyword,
			}
			if options.IndexSource {
				item["source"] = rawLine
			}
			appendBucket(payload, "modules", item)
			if elixirLineOpensBlock(keyword, trimmed) {
				scopes = append(scopes, elixirScope{
					kind:       "module",
					name:       name,
					lineNumber: lineNumber,
					item:       item,
				})
			}
			lastMeaningfulLine = trimmed
			continue
		}

		if keyword, name, args, openBlock, ok := parseElixirFunctionLine(trimmed); ok {
			item := map[string]any{
				"name":          name,
				"line_number":   lineNumber,
				"end_line":      lineNumber,
				"args":          args,
				"lang":          "elixir",
				"is_dependency": isDependency,
				"visibility":    "public",
				"type":          keyword,
				"decorators":    []string{},
			}
			if strings.HasSuffix(keyword, "p") {
				item["visibility"] = "private"
			}
			if moduleName, moduleLine := currentElixirModule(scopes); moduleName != "" {
				item["context"] = []any{moduleName, "module", moduleLine}
				item["context_type"] = "module"
				item["class_context"] = moduleName
			}
			if options.IndexSource {
				item["source"] = rawLine
				if docstring := elixirDocstringFromPreviousLine(lastMeaningfulLine); docstring != "" {
					item["docstring"] = docstring
				}
			}
			appendBucket(payload, "functions", item)
			if keyword == "defguard" || keyword == "defguardp" {
				guardExpression := trimmed
				if whenIndex := strings.Index(guardExpression, " when "); whenIndex >= 0 {
					guardExpression = guardExpression[whenIndex+len(" when "):]
				}
				currentContextName, currentContextType, currentContextLine := currentElixirContext(scopes)
				currentModuleName, _ := currentElixirModule(scopes)
				for _, match := range elixirCallPattern.FindAllStringSubmatchIndex(guardExpression, -1) {
					if len(match) < 4 {
						continue
					}
					name := guardExpression[match[2]:match[3]]
					if name == item["name"] {
						continue
					}
					args := elixirCallArgs(guardExpression, match[1]-1)
					appendUniqueElixirCall(
						payload,
						seenCalls,
						name,
						name,
						"",
						args,
						lineNumber,
						currentContextName,
						currentContextType,
						currentContextLine,
						currentModuleName,
						isDependency,
					)
				}
			}
			if openBlock {
				scopes = append(scopes, elixirScope{
					kind:       "function",
					name:       name,
					lineNumber: lineNumber,
					item:       item,
				})
			} else if options.IndexSource {
				item["source"] = rawLine
			}
			lastMeaningfulLine = trimmed
			continue
		}

		if keyword, paths, ok := parseElixirImportLine(trimmed); ok {
			for _, path := range paths {
				aliasName := any(nil)
				if keyword == "alias" && len(path) > 0 {
					aliasName = lastAliasSegment(path)
				}
				appendBucket(payload, "imports", map[string]any{
					"name":             path,
					"full_import_name": keyword + " " + path,
					"line_number":      lineNumber,
					"alias":            aliasName,
					"lang":             "elixir",
					"is_dependency":    isDependency,
					"import_type":      keyword,
				})
			}
			lastMeaningfulLine = trimmed
			continue
		}

		if matches := elixirAttributePattern.FindStringSubmatch(trimmed); len(matches) == 3 {
			attributeName := strings.TrimSpace(matches[1])
			if attributeName != "@doc" && attributeName != "@moduledoc" {
				item := map[string]any{
					"name":          attributeName,
					"line_number":   lineNumber,
					"end_line":      lineNumber,
					"lang":          "elixir",
					"is_dependency": isDependency,
					"value":         strings.TrimSpace(matches[2]),
				}
				if moduleName, moduleLine := currentElixirModule(scopes); moduleName != "" {
					item["context"] = []any{moduleName, "module", moduleLine}
					item["context_type"] = "module"
					item["class_context"] = moduleName
				}
				if options.IndexSource {
					item["source"] = rawLine
				}
				appendBucket(payload, "variables", item)
				lastMeaningfulLine = trimmed
				continue
			}
		}

		if strings.HasPrefix(trimmed, "#") {
			lastMeaningfulLine = trimmed
			continue
		}

		if isElixirDefinitionLine(trimmed) {
			lastMeaningfulLine = trimmed
			continue
		}

		currentContextName, currentContextType, currentContextLine := currentElixirContext(scopes)
		currentModuleName, _ := currentElixirModule(scopes)

		for _, match := range elixirScopedCall.FindAllStringSubmatchIndex(trimmed, -1) {
			if len(match) < 6 {
				continue
			}
			receiver := trimmed[match[2]:match[3]]
			name := trimmed[match[4]:match[5]]
			args := elixirCallArgs(trimmed, match[1]-1)
			appendUniqueElixirCall(
				payload,
				seenCalls,
				name,
				receiver+"."+name,
				receiver,
				args,
				lineNumber,
				currentContextName,
				currentContextType,
				currentContextLine,
				currentModuleName,
				isDependency,
			)
		}
		for _, match := range elixirCallPattern.FindAllStringSubmatchIndex(trimmed, -1) {
			if len(match) < 4 {
				continue
			}
			if match[0] > 0 && trimmed[match[0]-1] == '.' {
				continue
			}
			name := trimmed[match[2]:match[3]]
			switch name {
			case "def", "defp", "do", "fn":
				continue
			}
			args := elixirCallArgs(trimmed, match[1]-1)
			appendUniqueElixirCall(
				payload,
				seenCalls,
				name,
				name,
				"",
				args,
				lineNumber,
				currentContextName,
				currentContextType,
				currentContextLine,
				currentModuleName,
				isDependency,
			)
		}

		lastMeaningfulLine = trimmed
	}

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "modules")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")
	return payload, nil
}

func (e *Engine) preScanElixir(path string) ([]string, error) {
	payload, err := e.parseElixir(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "modules")
	slices.Sort(names)
	return names, nil
}

func (e *Engine) parseDart(path string, isDependency bool, options Options) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	payload := basePayload(path, "dart", isDependency)
	lines := strings.Split(string(source), "\n")
	seenVariables := make(map[string]struct{})
	seenCalls := make(map[string]struct{})

	for index, rawLine := range lines {
		lineNumber := index + 1
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" || strings.HasPrefix(trimmed, "//") {
			continue
		}

		if matches := dartImportPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			appendBucket(payload, "imports", map[string]any{
				"name":        matches[1],
				"line_number": lineNumber,
				"lang":        "dart",
			})
		}
		for _, pattern := range []*regexp.Regexp{dartClassPattern, dartMixinPattern, dartEnumPattern, dartExtensionPattern} {
			if matches := pattern.FindStringSubmatch(trimmed); len(matches) == 2 {
				appendBucket(payload, "classes", map[string]any{
					"name":        matches[1],
					"line_number": lineNumber,
					"end_line":    lineNumber,
					"lang":        "dart",
				})
			}
		}
		if matches := dartFunctionPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			switch name {
			case "if", "for", "while", "switch":
				continue
			}
			item := map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "dart",
				"decorators":  []string{},
			}
			if options.IndexSource {
				item["source"] = rawLine
			}
			appendBucket(payload, "functions", item)
		}
		if matches := dartVariablePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			if _, ok := seenVariables[name]; !ok {
				seenVariables[name] = struct{}{}
				appendBucket(payload, "variables", map[string]any{
					"name":        name,
					"line_number": lineNumber,
					"end_line":    lineNumber,
					"lang":        "dart",
				})
			}
		}
		for _, match := range dartCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			name := match[1]
			switch name {
			case "if", "for", "while", "switch":
				continue
			}
			appendUniqueRegexCall(payload, seenCalls, name, lineNumber, "dart")
		}
	}

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")
	return payload, nil
}

func (e *Engine) preScanDart(path string) ([]string, error) {
	payload, err := e.parseDart(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes")
	slices.Sort(names)
	return names, nil
}

type elixirScope struct {
	kind       string
	name       string
	lineNumber int
	item       map[string]any
}

func parseElixirModuleLine(trimmed string) (string, string, bool) {
	matches := elixirModulePattern.FindStringSubmatch(trimmed)
	if len(matches) != 3 {
		return "", "", false
	}
	keyword := matches[1]
	remainder := strings.TrimSpace(matches[2])
	if remainder == "" {
		return "", "", false
	}
	if index := strings.Index(remainder, ","); index >= 0 {
		remainder = strings.TrimSpace(remainder[:index])
	}
	if index := strings.Index(remainder, " do"); index >= 0 {
		remainder = strings.TrimSpace(remainder[:index])
	}
	fields := strings.Fields(remainder)
	if len(fields) == 0 {
		return "", "", false
	}
	return keyword, fields[0], true
}

func parseElixirFunctionLine(trimmed string) (string, string, []string, bool, bool) {
	matches := elixirFunctionPattern.FindStringSubmatch(trimmed)
	if len(matches) != 3 {
		return "", "", nil, false, false
	}
	keyword := matches[1]
	remainder := strings.TrimSpace(matches[2])
	if remainder == "" {
		return "", "", nil, false, false
	}

	name := remainder
	if index := strings.IndexAny(name, "(, \t"); index >= 0 {
		name = strings.TrimSpace(name[:index])
	}
	if name == "" {
		return "", "", nil, false, false
	}

	args := parseElixirArgs(remainder)
	openBlock := elixirLineOpensBlock(keyword, trimmed)
	return keyword, name, args, openBlock, true
}

func parseElixirImportLine(trimmed string) (string, []string, bool) {
	matches := elixirImportPattern.FindStringSubmatch(trimmed)
	if len(matches) != 3 {
		return "", nil, false
	}
	keyword := matches[1]
	remainder := strings.TrimSpace(matches[2])
	if remainder == "" {
		return "", nil, false
	}
	parts := splitElixirArgs(remainder)
	if len(parts) == 0 {
		return "", nil, false
	}
	remainder = strings.TrimSpace(parts[0])
	if keyword == "alias" {
		base := strings.TrimSpace(remainder)
		if base == "" {
			return "", nil, false
		}
		return keyword, expandElixirAliasPaths(base), true
	}
	fields := strings.Fields(remainder)
	if len(fields) == 0 {
		return "", nil, false
	}
	return keyword, []string{fields[0]}, true
}

func isElixirDefinitionLine(trimmed string) bool {
	for _, prefix := range []string{
		"defmodule ",
		"defprotocol ",
		"defimpl ",
		"def ",
		"defp ",
		"defmacro ",
		"defmacrop ",
		"defdelegate ",
		"defguard ",
		"defguardp ",
		"use ",
		"import ",
		"alias ",
		"require ",
	} {
		if strings.HasPrefix(trimmed, prefix) {
			return true
		}
	}
	return false
}

func elixirLineOpensBlock(keyword string, trimmed string) bool {
	switch keyword {
	case "defmodule", "defprotocol", "defimpl", "def", "defp", "defmacro", "defmacrop":
		return strings.Contains(trimmed, " do") && !strings.Contains(trimmed, ", do:")
	default:
		return false
	}
}

func parseElixirArgs(remainder string) []string {
	start := strings.Index(remainder, "(")
	if start < 0 {
		return []string{}
	}
	end := findMatchingParen(remainder, start)
	if end <= start {
		return []string{}
	}
	return splitElixirArgs(remainder[start+1 : end])
}

func elixirCallArgs(trimmed string, openParenIndex int) []string {
	if openParenIndex < 0 || openParenIndex >= len(trimmed) {
		return []string{}
	}
	end := findMatchingParen(trimmed, openParenIndex)
	if end <= openParenIndex {
		return []string{}
	}
	return splitElixirArgs(trimmed[openParenIndex+1 : end])
}

func findMatchingParen(text string, openParenIndex int) int {
	depth := 0
	inSingle := false
	inDouble := false
	inBacktick := false
	for index := openParenIndex; index < len(text); index++ {
		char := text[index]
		switch char {
		case '\\':
			if index+1 < len(text) {
				index++
			}
		case '\'':
			if !inDouble && !inBacktick {
				inSingle = !inSingle
			}
		case '"':
			if !inSingle && !inBacktick {
				inDouble = !inDouble
			}
		case '`':
			if !inSingle && !inDouble {
				inBacktick = !inBacktick
			}
		case '(':
			if !inSingle && !inDouble && !inBacktick {
				depth++
			}
		case ')':
			if !inSingle && !inDouble && !inBacktick {
				depth--
				if depth == 0 {
					return index
				}
			}
		}
	}
	return -1
}

func splitElixirArgs(body string) []string {
	trimmed := strings.TrimSpace(body)
	if trimmed == "" {
		return []string{}
	}

	args := make([]string, 0)
	current := strings.Builder{}
	depth := 0
	inSingle := false
	inDouble := false
	inBacktick := false

	flush := func() {
		value := strings.TrimSpace(current.String())
		if value != "" {
			args = append(args, value)
		}
		current.Reset()
	}

	for index := 0; index < len(trimmed); index++ {
		char := trimmed[index]
		switch char {
		case '\\':
			current.WriteByte(char)
			if index+1 < len(trimmed) {
				index++
				current.WriteByte(trimmed[index])
			}
			continue
		case '\'':
			if !inDouble && !inBacktick {
				inSingle = !inSingle
			}
		case '"':
			if !inSingle && !inBacktick {
				inDouble = !inDouble
			}
		case '`':
			if !inSingle && !inDouble {
				inBacktick = !inBacktick
			}
		case '(', '[', '{':
			if !inSingle && !inDouble && !inBacktick {
				depth++
			}
		case ')', ']', '}':
			if !inSingle && !inDouble && !inBacktick && depth > 0 {
				depth--
			}
		case ',':
			if depth == 0 && !inSingle && !inDouble && !inBacktick {
				flush()
				continue
			}
		}
		current.WriteByte(char)
	}
	flush()
	return args
}

func elixirDocstringFromPreviousLine(previous string) string {
	trimmed := strings.TrimSpace(previous)
	if trimmed == "" {
		return ""
	}
	if strings.HasPrefix(trimmed, "@doc") || strings.HasPrefix(trimmed, "@moduledoc") || strings.HasPrefix(trimmed, "#") {
		return trimmed
	}
	return ""
}

func currentElixirModule(scopes []elixirScope) (string, int) {
	for index := len(scopes) - 1; index >= 0; index-- {
		if scopes[index].kind == "module" {
			return scopes[index].name, scopes[index].lineNumber
		}
	}
	return "", 0
}

func currentElixirContext(scopes []elixirScope) (string, string, int) {
	for index := len(scopes) - 1; index >= 0; index-- {
		scope := scopes[index]
		if scope.kind == "function" {
			return scope.name, "function", scope.lineNumber
		}
		if scope.kind == "module" {
			return scope.name, "module", scope.lineNumber
		}
	}
	return "", "", 0
}

func popElixirScope(scopes []elixirScope) ([]elixirScope, elixirScope) {
	if len(scopes) == 0 {
		return scopes, elixirScope{}
	}
	popped := scopes[len(scopes)-1]
	return scopes[:len(scopes)-1], popped
}

func lastAliasSegment(name string) string {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" {
		return ""
	}
	parts := strings.Split(trimmed, ".")
	return parts[len(parts)-1]
}

func expandElixirAliasPaths(base string) []string {
	trimmed := strings.TrimSpace(base)
	if trimmed == "" {
		return nil
	}
	openIndex := strings.Index(trimmed, "{")
	closeIndex := strings.Index(trimmed, "}")
	if openIndex < 0 || closeIndex < 0 || closeIndex <= openIndex {
		return []string{trimmed}
	}

	prefix := strings.TrimSpace(trimmed[:openIndex])
	suffix := strings.TrimSpace(trimmed[closeIndex+1:])
	options := splitElixirArgs(trimmed[openIndex+1 : closeIndex])
	expanded := make([]string, 0, len(options))
	for _, option := range options {
		value := strings.TrimSpace(option)
		if value == "" {
			continue
		}
		name := strings.TrimSpace(prefix + value + suffix)
		name = strings.TrimSuffix(name, ".")
		if name != "" {
			expanded = append(expanded, name)
		}
	}
	if len(expanded) == 0 {
		return []string{trimmed}
	}
	return expanded
}

func appendUniqueElixirCall(
	payload map[string]any,
	seen map[string]struct{},
	name string,
	fullName string,
	inferredObjType string,
	args []string,
	lineNumber int,
	contextName string,
	contextType string,
	contextLine int,
	classContext string,
	isDependency bool,
) {
	if strings.TrimSpace(fullName) == "" {
		return
	}
	if _, ok := seen[fullName]; ok {
		return
	}
	seen[fullName] = struct{}{}

	item := map[string]any{
		"name":          name,
		"full_name":     fullName,
		"line_number":   lineNumber,
		"args":          args,
		"lang":          "elixir",
		"is_dependency": isDependency,
	}
	if inferredObjType != "" {
		item["inferred_obj_type"] = inferredObjType
	} else {
		item["inferred_obj_type"] = nil
	}
	if contextName != "" && contextType != "" {
		item["context"] = []any{contextName, contextType, contextLine}
	}
	if classContext != "" {
		item["class_context"] = classContext
	}
	appendBucket(payload, "function_calls", item)
}

func appendUniqueRegexCall(
	payload map[string]any,
	seen map[string]struct{},
	fullName string,
	lineNumber int,
	lang string,
) {
	if strings.TrimSpace(fullName) == "" {
		return
	}
	if _, ok := seen[fullName]; ok {
		return
	}
	seen[fullName] = struct{}{}
	appendBucket(payload, "function_calls", map[string]any{
		"name":        fullName,
		"full_name":   fullName,
		"line_number": lineNumber,
		"lang":        lang,
	})
}

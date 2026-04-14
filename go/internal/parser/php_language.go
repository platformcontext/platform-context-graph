package parser

import (
	"regexp"
	"slices"
	"strings"
)

var (
	phpNamespacePattern     = regexp.MustCompile(`^\s*namespace\s+([^;]+);`)
	phpUsePattern           = regexp.MustCompile(`^\s*use\s+([^;]+);`)
	phpTypePattern          = regexp.MustCompile(`^\s*(?:abstract\s+|final\s+)?(class|interface|trait)\s+([A-Za-z_]\w*)(.*)$`)
	phpFunctionPattern      = regexp.MustCompile(`^\s*(?:public\s+|protected\s+|private\s+|static\s+|abstract\s+|final\s+|readonly\s+)*function\s+([A-Za-z_]\w*)\s*\(`)
	phpVariablePattern      = regexp.MustCompile(`\$[A-Za-z_]\w*`)
	phpTypedVariablePattern = regexp.MustCompile(`(?:(?:public|protected|private|readonly|static)\s+)*([?A-Za-z_\\][\w\\|?]*)\s+\$[A-Za-z_]\w*`)
	phpMethodCallPattern    = regexp.MustCompile(`(\$[A-Za-z_]\w*(?:->\w+)+)\s*\(`)
	phpStaticCallPattern    = regexp.MustCompile(`\b([A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*)::([A-Za-z_]\w*)\s*\(`)
	phpNewCallPattern       = regexp.MustCompile(`\bnew\s+([A-Za-z_\\]\w*(?:\\[A-Za-z_]\w*)*)\s*\(`)
	phpFunctionCallPattern  = regexp.MustCompile(`\b([A-Za-z_]\w*)\s*\(`)
	phpVariableTypePattern  = regexp.MustCompile(`\$\w+\s*=\s*new\s+([A-Za-z_\\]\w*(?:\\[A-Za-z_]\w*)*)\s*\(`)
)

type phpScopedContext struct {
	kind       string
	name       string
	braceDepth int
	lineNumber int
}

func currentPHPScopedName(stack []phpScopedContext, kinds ...string) string {
	for index := len(stack) - 1; index >= 0; index-- {
		for _, kind := range kinds {
			if stack[index].kind == kind {
				return stack[index].name
			}
		}
	}
	return ""
}

func popPHPCompletedScopes(stack []phpScopedContext, braceDepth int) []phpScopedContext {
	for len(stack) > 0 && braceDepth < stack[len(stack)-1].braceDepth {
		stack = stack[:len(stack)-1]
	}
	return stack
}

func (e *Engine) parsePHP(path string, isDependency bool, options Options) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	payload := basePayload(path, "php", isDependency)
	payload["traits"] = []map[string]any{}
	payload["interfaces"] = []map[string]any{}

	lines := strings.Split(string(source), "\n")
	namespace := ""
	braceDepth := 0
	stack := make([]phpScopedContext, 0)
	var pendingFunction *phpScopedContext
	seenVariables := make(map[string]struct{})
	seenCalls := make(map[string]struct{})

	for index, rawLine := range lines {
		lineNumber := index + 1
		trimmed := strings.TrimSpace(rawLine)
		if pendingFunction != nil && strings.Contains(rawLine, "{") {
			stack = append(stack, phpScopedContext{
				kind:       pendingFunction.kind,
				name:       pendingFunction.name,
				braceDepth: braceDepth + max(1, strings.Count(rawLine, "{")),
				lineNumber: pendingFunction.lineNumber,
			})
			pendingFunction = nil
		}
		if trimmed == "" || strings.HasPrefix(trimmed, "//") || strings.HasPrefix(trimmed, "#") {
			braceDepth += braceDelta(rawLine)
			stack = popPHPCompletedScopes(stack, braceDepth)
			continue
		}

		if matches := phpNamespacePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			namespace = strings.TrimSpace(matches[1])
		}

		if matches := phpUsePattern.FindStringSubmatch(trimmed); len(matches) == 2 && currentPHPScopedName(stack, "class_declaration", "interface_declaration", "trait_declaration") == "" {
			importName, alias := parsePHPImport(matches[1])
			appendBucket(payload, "imports", map[string]any{
				"name":             importName,
				"full_import_name": trimmed,
				"line_number":      lineNumber,
				"alias":            alias,
				"context":          []any{nil, nil},
				"lang":             "php",
				"is_dependency":    false,
			})
		}

		if matches := phpTypePattern.FindStringSubmatch(trimmed); len(matches) == 4 {
			name := matches[2]
			bases := parsePHPBases(matches[1], matches[3])
			item := map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "php",
			}
			if len(bases) > 0 {
				item["bases"] = bases
			}
			switch matches[1] {
			case "class":
				appendBucket(payload, "classes", item)
				stack = append(stack, phpScopedContext{kind: "class_declaration", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{")), lineNumber: lineNumber})
			case "interface":
				appendBucket(payload, "interfaces", item)
				stack = append(stack, phpScopedContext{kind: "interface_declaration", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{")), lineNumber: lineNumber})
			case "trait":
				appendBucket(payload, "traits", item)
				stack = append(stack, phpScopedContext{kind: "trait_declaration", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{")), lineNumber: lineNumber})
			}
		}

		if matches := phpFunctionPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			functionKind := "function_definition"
			if currentPHPScopedName(stack, "class_declaration", "interface_declaration", "trait_declaration") != "" {
				functionKind = "method_declaration"
			}
			item := map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "php",
				"decorators":  []string{},
				"parameters":  extractPHPParameters(lines, index, rawLine),
			}
			if classContext := currentPHPScopedName(stack, "class_declaration", "interface_declaration", "trait_declaration"); classContext != "" {
				item["class_context"] = classContext
			}
			if options.IndexSource {
				item["source"] = collectPHPBlockSource(lines, index)
			}
			appendBucket(payload, "functions", item)
			if strings.Contains(rawLine, "{") {
				stack = append(stack, phpScopedContext{kind: functionKind, name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{")), lineNumber: lineNumber})
			} else {
				pendingFunction = &phpScopedContext{kind: functionKind, name: name, lineNumber: lineNumber}
			}
		}

		for _, variable := range phpVariablePattern.FindAllString(rawLine, -1) {
			if variable == "$this" {
				continue
			}
			if _, ok := seenVariables[variable]; ok {
				continue
			}
			seenVariables[variable] = struct{}{}
			contextName, contextKind, _ := currentPHPContext(stack)
			item := map[string]any{
				"name":        variable,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "php",
				"type":        inferPHPVariableType(rawLine, variable),
			}
			if contextName != "" {
				item["context"] = contextName
			}
			switch contextKind {
			case "class_declaration", "interface_declaration", "trait_declaration":
				item["class_context"] = contextName
			default:
				item["class_context"] = nil
			}
			appendBucket(payload, "variables", item)
		}

		contextName, contextKind, contextLine := currentPHPContext(stack)
		currentClassContext := currentPHPScopedName(stack, "class_declaration", "interface_declaration", "trait_declaration")
		for _, match := range phpMethodCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			callName := lastPathSegment(match[1], "->")
			fullName := normalizePHPMethodCall(match[1])
			appendUniquePHPCall(payload, seenCalls, callName, fullName, lineNumber, extractPHPCallArgs(lines, index, rawLine, match[0]), contextName, contextKind, contextLine, "")
		}
		for _, match := range phpStaticCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 3 {
				continue
			}
			receiver := normalizePHPStaticReceiver(match[1], currentClassContext)
			if receiver == "" {
				continue
			}
			methodName := strings.TrimSpace(match[2])
			fullName := receiver + "." + methodName
			appendUniquePHPCall(payload, seenCalls, methodName, fullName, lineNumber, extractPHPCallArgs(lines, index, rawLine, match[0]), contextName, contextKind, contextLine, receiver)
		}
		for _, match := range phpNewCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			className := lastPathSegment(match[1], `\`)
			appendUniquePHPCall(payload, seenCalls, className, className, lineNumber, extractPHPCallArgs(lines, index, rawLine, match[0]), contextName, contextKind, contextLine, "")
		}
		if !strings.Contains(trimmed, "->") && !strings.Contains(trimmed, "::") && !strings.Contains(trimmed, "new ") && !phpFunctionPattern.MatchString(trimmed) {
			for _, match := range phpFunctionCallPattern.FindAllStringSubmatch(trimmed, -1) {
				if len(match) != 2 {
					continue
				}
				name := match[1]
				switch name {
				case "function", "if", "foreach", "for", "switch", "echo", "require_once":
					continue
				}
				appendUniquePHPCall(payload, seenCalls, name, name, lineNumber, extractPHPCallArgs(lines, index, rawLine, match[0]), contextName, contextKind, contextLine, "")
			}
		}

		braceDepth += braceDelta(rawLine)
		stack = popPHPCompletedScopes(stack, braceDepth)
	}

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "traits")
	sortNamedBucket(payload, "interfaces")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")

	if namespace != "" {
		payload["namespace"] = namespace
	}

	return payload, nil
}

func (e *Engine) preScanPHP(path string) ([]string, error) {
	payload, err := e.parsePHP(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes", "traits", "interfaces")
	slices.Sort(names)
	return names, nil
}

func appendUniquePHPCall(
	payload map[string]any,
	seen map[string]struct{},
	name string,
	fullName string,
	lineNumber int,
	args []string,
	contextName string,
	contextKind string,
	contextLine int,
	inferredObjType string,
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
		"context":       []any{contextName, contextKind, contextLine},
		"lang":          "php",
		"is_dependency": false,
	}
	if inferredObjType != "" {
		item["inferred_obj_type"] = inferredObjType
	} else {
		item["inferred_obj_type"] = nil
	}
	if contextKind == "class_declaration" || contextKind == "interface_declaration" || contextKind == "trait_declaration" {
		item["class_context"] = []any{contextName, contextLine}
	} else {
		item["class_context"] = []any{nil, nil}
	}
	appendBucket(payload, "function_calls", item)
}

func normalizePHPMethodCall(raw string) string {
	parts := strings.Split(raw, "->")
	if len(parts) <= 1 {
		return raw
	}
	return strings.Join(parts[:len(parts)-1], "->") + "." + parts[len(parts)-1]
}

func normalizePHPStaticReceiver(raw string, classContext string) string {
	receiver := strings.TrimSpace(raw)
	if receiver == "" {
		return ""
	}

	switch receiver {
	case "self", "static":
		if classContext != "" {
			return classContext
		}
	case "parent":
		return receiver
	}

	return strings.TrimPrefix(receiver, `\`)
}

func parsePHPImport(raw string) (string, string) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "", ""
	}
	parts := strings.Fields(trimmed)
	if len(parts) == 0 {
		return "", ""
	}
	name := strings.TrimSpace(parts[0])
	alias := ""
	if len(parts) >= 3 && strings.EqualFold(parts[1], "as") {
		alias = strings.TrimSpace(parts[2])
	}
	return name, alias
}

func parsePHPBases(kind string, tail string) []string {
	remaining := strings.TrimSpace(tail)
	if remaining == "" {
		return nil
	}

	remaining = strings.TrimSpace(strings.TrimSuffix(remaining, "{"))
	if remaining == "" {
		return nil
	}

	var rawBases string
	switch kind {
	case "class":
		if index := strings.Index(remaining, "extends"); index >= 0 {
			afterExtends := strings.TrimSpace(remaining[index+len("extends"):])
			if split := strings.Index(afterExtends, "implements"); split >= 0 {
				extendsBases := appendPHPBaseList(strings.TrimSpace(afterExtends[:split]))
				implementsBases := appendPHPBaseList(strings.TrimSpace(afterExtends[split+len("implements"):]))
				return append(extendsBases, implementsBases...)
			}
			rawBases = afterExtends
		}
		if index := strings.Index(remaining, "implements"); index >= 0 {
			rawBases = strings.TrimSpace(remaining[index+len("implements"):])
		}
	case "interface":
		if index := strings.Index(remaining, "extends"); index >= 0 {
			rawBases = strings.TrimSpace(remaining[index+len("extends"):])
		}
	}

	if rawBases == "" {
		return nil
	}
	return appendPHPBaseList(rawBases)
}

func appendPHPBaseList(raw string) []string {
	segments := strings.Split(raw, ",")
	bases := make([]string, 0, len(segments))
	for _, segment := range segments {
		trimmed := strings.TrimSpace(segment)
		if trimmed == "" {
			continue
		}
		bases = append(bases, lastPathSegment(trimmed, `\`))
	}
	return bases
}

func extractPHPParameters(lines []string, startIndex int, rawLine string) []string {
	signature := rawLine
	for index := startIndex; index < len(lines) && !strings.Contains(signature, ")"); index++ {
		if index == startIndex {
			continue
		}
		signature += " " + strings.TrimSpace(lines[index])
	}
	start := strings.Index(signature, "(")
	end := strings.LastIndex(signature, ")")
	if start < 0 || end < 0 || end <= start {
		return nil
	}
	rawParams := signature[start+1 : end]
	if strings.TrimSpace(rawParams) == "" {
		return []string{}
	}
	parts := strings.Split(rawParams, ",")
	parameters := make([]string, 0, len(parts))
	for _, part := range parts {
		match := regexp.MustCompile(`\$(\w+)`).FindStringSubmatch(part)
		if len(match) != 2 {
			continue
		}
		parameters = append(parameters, "$"+match[1])
	}
	return parameters
}

func collectPHPBlockSource(lines []string, startIndex int) string {
	if startIndex < 0 || startIndex >= len(lines) {
		return ""
	}

	var builder strings.Builder
	depth := 0
	sawOpenBrace := false
	for index := startIndex; index < len(lines); index++ {
		if index > startIndex {
			builder.WriteString("\n")
		}
		builder.WriteString(lines[index])
		if strings.Contains(lines[index], "{") {
			sawOpenBrace = true
		}
		depth += braceDelta(lines[index])
		if sawOpenBrace && depth <= 0 {
			break
		}
	}
	return builder.String()
}

func currentPHPContext(stack []phpScopedContext) (string, string, int) {
	for index := len(stack) - 1; index >= 0; index-- {
		switch stack[index].kind {
		case "function_definition", "method_declaration", "class_declaration", "interface_declaration", "trait_declaration":
			return stack[index].name, stack[index].kind, stack[index].lineNumber
		}
	}
	return "", "", 0
}

func inferPHPVariableType(rawLine string, variable string) string {
	if matches := phpTypedVariablePattern.FindStringSubmatch(rawLine); len(matches) == 2 && strings.Contains(rawLine, variable) {
		return normalizePHPTypeName(matches[1])
	}
	if matches := phpVariableTypePattern.FindStringSubmatch(rawLine); len(matches) == 2 {
		return normalizePHPTypeName(matches[1])
	}
	return "mixed"
}

func extractPHPCallArgs(lines []string, startIndex int, rawLine string, callText string) []string {
	start := strings.Index(rawLine, callText)
	if start < 0 {
		return nil
	}
	remainder := rawLine[start+len(callText):]
	if startIndex+1 < len(lines) {
		remainder += "\n" + strings.Join(lines[startIndex+1:], "\n")
	}
	rawArgs, ok := collectPHPCallArgumentSource(remainder)
	if !ok {
		return nil
	}
	rawArgs = strings.TrimSpace(rawArgs)
	if rawArgs == "" {
		return []string{}
	}
	return splitPHPCallArguments(rawArgs)
}

func collectPHPCallArgumentSource(raw string) (string, bool) {
	if raw == "" {
		return "", false
	}

	depth := 1
	inSingleQuote := false
	inDoubleQuote := false
	escaped := false
	var builder strings.Builder

	for index := 0; index < len(raw); index++ {
		ch := raw[index]
		if escaped {
			builder.WriteByte(ch)
			escaped = false
			continue
		}
		if inSingleQuote {
			builder.WriteByte(ch)
			if ch == '\\' {
				escaped = true
				continue
			}
			if ch == '\'' {
				inSingleQuote = false
			}
			continue
		}
		if inDoubleQuote {
			builder.WriteByte(ch)
			if ch == '\\' {
				escaped = true
				continue
			}
			if ch == '"' {
				inDoubleQuote = false
			}
			continue
		}

		switch ch {
		case '\'':
			inSingleQuote = true
			builder.WriteByte(ch)
		case '"':
			inDoubleQuote = true
			builder.WriteByte(ch)
		case '(':
			depth++
			builder.WriteByte(ch)
		case ')':
			depth--
			if depth == 0 {
				return builder.String(), true
			}
			builder.WriteByte(ch)
		default:
			builder.WriteByte(ch)
		}
	}

	return "", false
}

func splitPHPCallArguments(raw string) []string {
	args := make([]string, 0)
	var current strings.Builder
	parenDepth := 0
	bracketDepth := 0
	braceDepth := 0
	inSingleQuote := false
	inDoubleQuote := false
	escaped := false

	flush := func() {
		trimmed := strings.TrimSpace(current.String())
		if trimmed != "" {
			args = append(args, trimmed)
		}
		current.Reset()
	}

	for index := 0; index < len(raw); index++ {
		ch := raw[index]
		if escaped {
			current.WriteByte(ch)
			escaped = false
			continue
		}
		if inSingleQuote {
			current.WriteByte(ch)
			if ch == '\\' {
				escaped = true
				continue
			}
			if ch == '\'' {
				inSingleQuote = false
			}
			continue
		}
		if inDoubleQuote {
			current.WriteByte(ch)
			if ch == '\\' {
				escaped = true
				continue
			}
			if ch == '"' {
				inDoubleQuote = false
			}
			continue
		}

		switch ch {
		case '\'':
			inSingleQuote = true
			current.WriteByte(ch)
		case '"':
			inDoubleQuote = true
			current.WriteByte(ch)
		case '(':
			parenDepth++
			current.WriteByte(ch)
		case ')':
			if parenDepth > 0 {
				parenDepth--
			}
			current.WriteByte(ch)
		case '[':
			bracketDepth++
			current.WriteByte(ch)
		case ']':
			if bracketDepth > 0 {
				bracketDepth--
			}
			current.WriteByte(ch)
		case '{':
			braceDepth++
			current.WriteByte(ch)
		case '}':
			if braceDepth > 0 {
				braceDepth--
			}
			current.WriteByte(ch)
		case ',':
			if parenDepth == 0 && bracketDepth == 0 && braceDepth == 0 {
				flush()
				continue
			}
			current.WriteByte(ch)
		default:
			current.WriteByte(ch)
		}
	}

	flush()
	return args
}

func normalizePHPTypeName(raw string) string {
	trimmed := strings.TrimSpace(raw)
	trimmed = strings.TrimPrefix(trimmed, "?")
	if index := strings.Index(trimmed, "|"); index >= 0 {
		parts := strings.Split(trimmed, "|")
		normalized := make([]string, 0, len(parts))
		for _, part := range parts {
			part = strings.TrimSpace(part)
			if part == "" {
				continue
			}
			normalized = append(normalized, normalizePHPTypeName(part))
		}
		return strings.Join(normalized, "|")
	}
	return lastPathSegment(trimmed, `\`)
}

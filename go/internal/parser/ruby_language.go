package parser

import (
	"regexp"
	"slices"
	"strings"
)

var (
	rubyModulePattern      = regexp.MustCompile(`^\s*module\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)`)
	rubyClassPattern       = regexp.MustCompile(`^\s*class\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)(?:\s*<\s*([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*))?`)
	rubyFunctionPattern    = regexp.MustCompile(`^\s*def\s+(self\.)?([A-Za-z_]\w*[!?=]?)`)
	rubyRequirePattern     = regexp.MustCompile(`^\s*require\s+['"]([^'"]+)['"]`)
	rubyIncludePattern     = regexp.MustCompile(`^\s*include\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)`)
	rubyInstanceVarPattern = regexp.MustCompile(`@\w+`)
	rubyScopedCallPattern  = regexp.MustCompile(`([A-Z][A-Za-z0-9_:]*\.[A-Za-z_]\w*[!?=]?)\(`)
)

type rubyBlock struct {
	kind string
	name string
}

func (e *Engine) parseRuby(path string, isDependency bool, options Options) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	payload := basePayload(path, "ruby", isDependency)
	payload["modules"] = []map[string]any{}
	payload["module_inclusions"] = []map[string]any{}
	payload["framework_semantics"] = map[string]any{"frameworks": []string{}}

	lines := strings.Split(string(source), "\n")
	blocks := make([]rubyBlock, 0)
	seenVariables := make(map[string]struct{})
	seenCalls := make(map[string]struct{})

	for index, rawLine := range lines {
		lineNumber := index + 1
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}

		if trimmed == "end" {
			if len(blocks) > 0 {
				blocks = blocks[:len(blocks)-1]
			}
			continue
		}

		if matches := rubyModulePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := rubyLastSegment(matches[1])
			appendBucket(payload, "modules", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "ruby",
			})
			blocks = append(blocks, rubyBlock{kind: "module", name: name})
			continue
		}

		if matches := rubyClassPattern.FindStringSubmatch(trimmed); len(matches) >= 2 {
			name := rubyLastSegment(matches[1])
			item := map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "ruby",
				"type":        "class",
			}
			if len(matches) >= 3 && strings.TrimSpace(matches[2]) != "" {
				item["bases"] = []string{rubyLastSegment(matches[2])}
			}
			appendBucket(payload, "classes", item)
			blocks = append(blocks, rubyBlock{kind: "class", name: name})
			continue
		}

		if matches := rubyFunctionPattern.FindStringSubmatch(trimmed); len(matches) == 3 {
			name := matches[2]
			item := map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "ruby",
				"decorators":  []string{},
			}
			if className := rubyCurrentBlockName(blocks, "class"); className != "" {
				item["class_context"] = className
			}
			if options.IndexSource {
				item["source"] = rawLine
			}
			appendBucket(payload, "functions", item)
			blocks = append(blocks, rubyBlock{kind: "def", name: name})
			continue
		}

		if matches := rubyRequirePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			appendBucket(payload, "imports", map[string]any{
				"name":        matches[1],
				"line_number": lineNumber,
				"lang":        "ruby",
			})
		}

		if matches := rubyIncludePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			className := rubyCurrentBlockName(blocks, "class")
			if className != "" {
				appendBucket(payload, "module_inclusions", map[string]any{
					"class":  className,
					"module": rubyLastSegment(matches[1]),
				})
			}
		}

		for _, variable := range rubyInstanceVarPattern.FindAllString(rawLine, -1) {
			if _, ok := seenVariables[variable]; ok {
				continue
			}
			seenVariables[variable] = struct{}{}
			appendBucket(payload, "variables", map[string]any{
				"name":        variable,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "ruby",
			})
		}

		for _, call := range rubyScopedCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(call) != 2 {
				continue
			}
			fullName := call[1]
			if _, ok := seenCalls[fullName]; ok {
				continue
			}
			seenCalls[fullName] = struct{}{}
			appendBucket(payload, "function_calls", map[string]any{
				"name":        fullName,
				"full_name":   fullName,
				"line_number": lineNumber,
				"lang":        "ruby",
			})
		}
	}

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "modules")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")

	return payload, nil
}

func (e *Engine) preScanRuby(path string) ([]string, error) {
	payload, err := e.parseRuby(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes", "modules")
	slices.Sort(names)
	return names, nil
}

func rubyCurrentBlockName(blocks []rubyBlock, kind string) string {
	for index := len(blocks) - 1; index >= 0; index-- {
		if blocks[index].kind == kind {
			return blocks[index].name
		}
	}
	return ""
}

func rubyLastSegment(name string) string {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" {
		return ""
	}
	segments := strings.Split(trimmed, "::")
	return segments[len(segments)-1]
}

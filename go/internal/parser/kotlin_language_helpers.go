package parser

import (
	"regexp"
	"strings"
)

var kotlinPrimaryConstructorPropertyPattern = regexp.MustCompile(
	`(?m)(?:^|,)\s*(?:(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s+)*)*(?:(?:private|public|protected|internal|override|open|final|const|lateinit)\s+)*(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`,
)

func kotlinPrimaryConstructorPropertyTypes(line string) map[string]string {
	trimmed := strings.TrimSpace(line)
	if trimmed == "" {
		return nil
	}

	openIndex := strings.Index(trimmed, "(")
	if openIndex < 0 {
		return nil
	}
	closeIndex := kotlinMatchingParenIndex(trimmed, openIndex)
	if closeIndex <= openIndex {
		return nil
	}

	constructor := trimmed[openIndex+1 : closeIndex]
	matches := kotlinPrimaryConstructorPropertyPattern.FindAllStringSubmatch(constructor, -1)
	if len(matches) == 0 {
		return nil
	}

	properties := make(map[string]string, len(matches))
	for _, match := range matches {
		if len(match) != 3 {
			continue
		}
		name := strings.TrimSpace(match[1])
		typ := strings.TrimSpace(match[2])
		if name == "" || typ == "" {
			continue
		}
		properties[name] = typ
	}
	if len(properties) == 0 {
		return nil
	}
	return properties
}

func kotlinMatchingParenIndex(value string, openIndex int) int {
	if openIndex < 0 || openIndex >= len(value) {
		return -1
	}

	depth := 0
	for index, char := range value[openIndex:] {
		switch char {
		case '(':
			depth++
		case ')':
			depth--
			if depth == 0 {
				return openIndex + index
			}
		}
	}

	return -1
}

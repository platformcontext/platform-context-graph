package parser

import (
	"regexp"
	"strings"
)

var kotlinReceiverPreservingScopeFunctionPattern = regexp.MustCompile(
	`(?s)^(.*)\.(?:also|apply)\s*\{.*\}\s*$`,
)

func kotlinStripReceiverPreservingScopeFunctions(expression string) string {
	expression = strings.TrimSpace(expression)
	for {
		matches := kotlinReceiverPreservingScopeFunctionPattern.FindStringSubmatch(expression)
		if len(matches) != 2 {
			return expression
		}
		expression = strings.TrimSpace(matches[1])
	}
}

package query

import (
	"regexp"
	"sort"
	"strings"
)

var workflowDeliveryFamilyPatterns = []struct {
	family string
	regex  *regexp.Regexp
}{
	{family: "terraform", regex: regexp.MustCompile(`(^|[;&|]\s*)terraform(\s|$)`)},
	{family: "terragrunt", regex: regexp.MustCompile(`(^|[;&|]\s*)terragrunt(\s|$)`)},
	{family: "helm", regex: regexp.MustCompile(`(^|[;&|]\s*)helm(\s|$)`)},
	{family: "kubectl", regex: regexp.MustCompile(`(^|[;&|]\s*)kubectl(\s|$)`)},
	{family: "ansible", regex: regexp.MustCompile(`(^|[;&|]\s*)ansible-playbook(\s|$)`)},
	{family: "argocd", regex: regexp.MustCompile(`(^|[;&|]\s*)argocd(\s|$)`)},
	{family: "docker_compose", regex: regexp.MustCompile(`(^|[;&|]\s*)(docker\s+compose|docker-compose)(\s|$)`)},
}

func workflowDeliveryCommandFamilies(runCommands []string) []string {
	families := make([]string, 0, len(workflowDeliveryFamilyPatterns)+1)
	seen := make(map[string]struct{}, len(workflowDeliveryFamilyPatterns)+1)

	for _, command := range runCommands {
		normalized := normalizeWorkflowCommand(command)
		if normalized == "" || strings.HasPrefix(normalized, "echo ") {
			continue
		}
		for _, pattern := range workflowDeliveryFamilyPatterns {
			if !pattern.regex.MatchString(normalized) {
				continue
			}
			if _, exists := seen[pattern.family]; exists {
				continue
			}
			seen[pattern.family] = struct{}{}
			families = append(families, pattern.family)
		}
		if strings.Contains(normalized, "docker build") ||
			strings.Contains(normalized, "docker run") ||
			strings.Contains(normalized, "docker push") ||
			strings.Contains(normalized, "docker pull") ||
			strings.Contains(normalized, "docker login") ||
			strings.Contains(normalized, "docker tag") {
			if _, exists := seen["docker"]; !exists {
				seen["docker"] = struct{}{}
				families = append(families, "docker")
			}
		}
	}

	if len(families) == 0 {
		return nil
	}
	sort.Strings(families)
	return families
}

func normalizeWorkflowCommand(command string) string {
	normalized := strings.ToLower(strings.TrimSpace(command))
	normalized = strings.ReplaceAll(normalized, "\n", " ")
	normalized = strings.ReplaceAll(normalized, "\t", " ")
	return strings.Join(strings.Fields(normalized), " ")
}

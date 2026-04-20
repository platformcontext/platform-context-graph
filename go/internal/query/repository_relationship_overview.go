package query

import (
	"slices"
	"strings"
)

func buildRepositoryRelationshipOverview(relationships []map[string]any) map[string]any {
	rows := make([]map[string]any, 0, len(relationships))
	for _, relationship := range relationships {
		relType := StringVal(relationship, "type")
		targetName := StringVal(relationship, "target_name")
		targetID := StringVal(relationship, "target_id")
		evidenceType := StringVal(relationship, "evidence_type")
		if relType == "" && targetName == "" && targetID == "" && evidenceType == "" {
			continue
		}
		row := map[string]any{
			"type":        relType,
			"target_name": targetName,
			"target_id":   targetID,
		}
		if evidenceType != "" {
			row["evidence_type"] = evidenceType
		}
		rows = append(rows, row)
	}

	if len(rows) == 0 {
		return nil
	}

	slices.SortFunc(rows, func(left, right map[string]any) int {
		if cmp := strings.Compare(StringVal(left, "type"), StringVal(right, "type")); cmp != 0 {
			return cmp
		}
		if cmp := strings.Compare(StringVal(left, "target_name"), StringVal(right, "target_name")); cmp != 0 {
			return cmp
		}
		return strings.Compare(StringVal(left, "evidence_type"), StringVal(right, "evidence_type"))
	})

	controllerDriven := filterRepositoryRelationshipsByEvidencePrefix(rows, controllerEvidenceTypePrefixes...)
	workflowDriven := filterRepositoryRelationshipsByEvidence(rows, "github_actions_")
	iacDriven := filterRepositoryRelationshipsByEvidencePrefix(rows, iacEvidenceTypePrefixes...)
	otherTyped := excludeRepositoryRelationships(rows, controllerDriven, workflowDriven, iacDriven)

	overview := map[string]any{
		"relationship_count": len(rows),
		"relationships":      rows,
		"relationship_types": uniqueRelationshipStrings(rows, "type"),
		"evidence_types":     uniqueRelationshipStrings(rows, "evidence_type"),
	}
	if len(controllerDriven) > 0 {
		overview["controller_driven"] = controllerDriven
	}
	if len(workflowDriven) > 0 {
		overview["workflow_driven"] = workflowDriven
	}
	if len(iacDriven) > 0 {
		overview["iac_driven"] = iacDriven
	}
	if len(otherTyped) > 0 {
		overview["other_relationships"] = otherTyped
	}
	if story := buildRepositoryRelationshipStory(overview); story != "" {
		overview["story"] = story
	}

	return overview
}

func buildRepositoryRelationshipStory(overview map[string]any) string {
	if len(overview) == 0 {
		return ""
	}

	parts := make([]string, 0, 3)
	if controllerDriven := mapSliceValue(overview, "controller_driven"); len(controllerDriven) > 0 {
		parts = append(parts, "Controller-driven relationships: "+joinSentenceFragments(relationshipSummaries(controllerDriven))+".")
	}
	if workflowDriven := mapSliceValue(overview, "workflow_driven"); len(workflowDriven) > 0 {
		parts = append(parts, "Workflow-driven relationships: "+joinSentenceFragments(relationshipSummaries(workflowDriven))+".")
	}
	if iacDriven := mapSliceValue(overview, "iac_driven"); len(iacDriven) > 0 {
		parts = append(parts, "IaC-driven relationships: "+joinSentenceFragments(relationshipSummaries(iacDriven))+".")
	}
	if otherRelationships := mapSliceValue(overview, "other_relationships"); len(otherRelationships) > 0 {
		parts = append(parts, "Other typed relationships: "+joinSentenceFragments(relationshipSummaries(otherRelationships))+".")
	}
	return strings.Join(parts, " ")
}

func filterRepositoryRelationshipsByEvidence(rows []map[string]any, prefix string) []map[string]any {
	return filterRepositoryRelationshipsByEvidencePrefix(rows, prefix)
}

func filterRepositoryRelationshipsByEvidencePrefix(rows []map[string]any, prefixes ...string) []map[string]any {
	filtered := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		evidenceType := StringVal(row, "evidence_type")
		for _, prefix := range prefixes {
			if strings.HasPrefix(evidenceType, prefix) {
				filtered = append(filtered, row)
				break
			}
		}
	}
	return filtered
}

func excludeRepositoryRelationships(rows []map[string]any, groups ...[]map[string]any) []map[string]any {
	if len(rows) == 0 {
		return nil
	}

	seen := make(map[string]struct{}, len(rows))
	for _, group := range groups {
		for _, row := range group {
			seen[repositoryRelationshipKey(row)] = struct{}{}
		}
	}

	filtered := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		if _, ok := seen[repositoryRelationshipKey(row)]; ok {
			continue
		}
		filtered = append(filtered, row)
	}
	return filtered
}

func repositoryRelationshipKey(row map[string]any) string {
	return strings.Join([]string{
		StringVal(row, "type"),
		StringVal(row, "target_name"),
		StringVal(row, "target_id"),
		StringVal(row, "evidence_type"),
	}, "|")
}

func relationshipSummaries(rows []map[string]any) []string {
	summaries := make([]string, 0, len(rows))
	for _, row := range rows {
		relType := StringVal(row, "type")
		targetName := StringVal(row, "target_name")
		evidenceType := StringVal(row, "evidence_type")
		parts := make([]string, 0, 3)
		if relType != "" {
			parts = append(parts, relType)
		}
		if targetName != "" {
			parts = append(parts, targetName)
		}
		if evidenceType != "" {
			parts = append(parts, "via "+evidenceType)
		}
		summaries = append(summaries, strings.Join(parts, " "))
	}
	return summaries
}

func uniqueRelationshipStrings(rows []map[string]any, key string) []string {
	values := make([]string, 0, len(rows))
	seen := map[string]struct{}{}
	for _, row := range rows {
		value := strings.TrimSpace(StringVal(row, key))
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		values = append(values, value)
	}
	slices.Sort(values)
	return values
}

var iacEvidenceTypePrefixes = []string{
	"docker_compose_",
	"dockerfile_",
	"helm_",
	"kustomize_",
	"terraform_",
	"terragrunt_",
}

var controllerEvidenceTypePrefixes = []string{
	"argocd_",
	"ansible_",
	"jenkins_",
}

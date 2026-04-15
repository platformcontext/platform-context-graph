package query

import "fmt"

func typeScriptDeclarationMergeSummary(label string, name string, metadata map[string]any) string {
	group, _ := metadata["declaration_merge_group"].(string)
	if group == "" || name == "" {
		return ""
	}

	count := IntVal(metadata, "declaration_merge_count")
	if count < 2 {
		return ""
	}

	kinds := metadataStringSlice(metadata, "declaration_merge_kinds")
	switch {
	case len(kinds) == 1 && kinds[0] == "interface":
		return fmt.Sprintf("%s %s participates in TypeScript declaration merging with %d same-name interface declarations.", label, name, count)
	case count == 2:
		if partner := declarationMergePartnerKind(label, kinds); partner != "" {
			return fmt.Sprintf("%s %s participates in TypeScript declaration merging with %s %s.", label, name, partner, group)
		}
	}

	return fmt.Sprintf("%s %s participates in TypeScript declaration merging with %d declarations.", label, name, count)
}

func declarationMergePartnerKind(label string, kinds []string) string {
	currentKind := declarationMergeEntityKind(label)
	for _, kind := range kinds {
		if kind == "" || kind == currentKind {
			continue
		}
		return kind
	}
	return ""
}

func declarationMergeEntityKind(label string) string {
	switch label {
	case "Class":
		return "class"
	case "Function":
		return "function"
	case "Interface":
		return "interface"
	case "Enum":
		return "enum"
	case "Module":
		return "namespace"
	default:
		return ""
	}
}

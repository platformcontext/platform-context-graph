package query

import (
	"fmt"
	"strings"
)

func buildEntitySemanticSummary(entity map[string]any) string {
	metadata, _ := entity["metadata"].(map[string]any)
	if len(metadata) == 0 {
		return ""
	}

	label := primaryEntityLabel(entity)
	name := StringVal(entity, "name")
	if label == "" || name == "" {
		return ""
	}

	switch label {
	case "TypeAnnotation":
		typeName, _ := metadata["type"].(string)
		if typeName == "" {
			return ""
		}
		return fmt.Sprintf("%s %s is annotated as %s.", label, name, typeName)
	case "Component":
		framework, _ := metadata["framework"].(string)
		if framework == "" {
			return ""
		}
		return fmt.Sprintf("%s %s is associated with the %s framework.", label, name, framework)
	}

	fragments := make([]string, 0, 4)
	pythonProfile := PythonSemanticProfileFromMetadata(label, metadata)
	if pythonProfile.Async {
		fragments = append(fragments, "is async")
	}
	if len(pythonProfile.Decorators) > 0 {
		fragments = append(fragments, "uses decorators "+strings.Join(pythonProfile.Decorators, ", "))
	}
	if params := metadataStringSlice(metadata, "type_parameters"); len(params) > 0 {
		fragments = append(fragments, "declares type parameters "+strings.Join(params, ", "))
	}
	jsSemantics := ExtractJavaScriptSemantics(metadata)
	if jsSemantics.MethodKind != "" {
		fragments = append(fragments, "has method kind "+jsSemantics.MethodKind)
	}
	if jsSemantics.Docstring != "" {
		fragments = append(fragments, fmt.Sprintf("is documented as %q", jsSemantics.Docstring))
	}

	if len(fragments) == 0 {
		return ""
	}
	if len(fragments) == 1 {
		return fmt.Sprintf("%s %s %s.", label, name, fragments[0])
	}
	return fmt.Sprintf("%s %s %s.", label, name, joinSentenceFragments(fragments))
}

func primaryEntityLabel(entity map[string]any) string {
	labels := StringSliceVal(entity, "labels")
	if len(labels) == 0 {
		return ""
	}
	return labels[0]
}

func joinSentenceFragments(parts []string) string {
	switch len(parts) {
	case 0:
		return ""
	case 1:
		return parts[0]
	case 2:
		return parts[0] + " and " + parts[1]
	default:
		return strings.Join(parts[:len(parts)-1], ", ") + ", and " + parts[len(parts)-1]
	}
}

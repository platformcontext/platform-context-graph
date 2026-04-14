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
	case "TerraformBlock":
		requiredProviders, _ := metadata["required_providers"].(string)
		if requiredProviders == "" {
			return ""
		}
		return fmt.Sprintf("%s %s requires providers %s.", label, name, requiredProviders)
	case "Typedef":
		typeName, _ := metadata["type"].(string)
		if typeName == "" {
			return ""
		}
		return fmt.Sprintf("%s %s aliases %s.", label, name, typeName)
	case "Annotation":
		kind, _ := metadata["kind"].(string)
		targetKind, _ := metadata["target_kind"].(string)
		if kind == "applied" && targetKind != "" {
			return fmt.Sprintf("%s %s is applied to a %s.", label, name, targetKind)
		}
		if kind == "declaration" {
			return fmt.Sprintf("%s %s declares an annotation type.", label, name)
		}
	case "Protocol":
		moduleKind, _ := metadata["module_kind"].(string)
		if moduleKind == "" {
			moduleKind = "protocol"
		}
		return fmt.Sprintf("%s %s is a %s.", label, name, strings.ReplaceAll(moduleKind, "_", " "))
	case "ImplBlock":
		kind, _ := metadata["kind"].(string)
		target, _ := metadata["target"].(string)
		trait, _ := metadata["trait"].(string)
		switch {
		case kind == "trait_impl" && trait != "" && target != "":
			return fmt.Sprintf("%s %s implements %s for %s.", label, name, trait, target)
		case kind != "" && target != "":
			return fmt.Sprintf("%s %s is a %s for %s.", label, name, strings.ReplaceAll(kind, "_", " "), target)
		}
	case "Component":
		framework, _ := metadata["framework"].(string)
		if framework == "" {
			return ""
		}
		return fmt.Sprintf("%s %s is associated with the %s framework.", label, name, framework)
	case "KustomizeOverlay":
		bases := metadataStringSlice(metadata, "bases")
		if len(bases) == 0 {
			return ""
		}
		return fmt.Sprintf("%s %s references bases %s.", label, name, strings.Join(bases, ", "))
	case "K8sResource":
		qualifiedName, _ := metadata["qualified_name"].(string)
		labels, _ := metadata["labels"].(string)
		switch {
		case qualifiedName != "" && labels != "":
			return fmt.Sprintf("%s %s is identified as %s and carries labels %s.", label, name, qualifiedName, labels)
		case qualifiedName != "":
			return fmt.Sprintf("%s %s is identified as %s.", label, name, qualifiedName)
		}
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
	if constructorKind, _ := metadata["constructor_kind"].(string); constructorKind != "" {
		fragments = append(fragments, fmt.Sprintf("is a %s constructor", strings.ReplaceAll(constructorKind, "_", " ")))
	}
	if semanticKind, _ := metadata["semantic_kind"].(string); semanticKind != "" {
		fragments = append(fragments, fmt.Sprintf("is a %s", strings.ReplaceAll(semanticKind, "_", " ")))
	}
	if moduleKind, _ := metadata["module_kind"].(string); moduleKind != "" {
		switch moduleKind {
		case "protocol_implementation":
			protocol, _ := metadata["protocol"].(string)
			implementedFor, _ := metadata["implemented_for"].(string)
			if protocol != "" && implementedFor != "" {
				fragments = append(fragments, fmt.Sprintf("is a protocol implementation for %s via %s", implementedFor, protocol))
			} else {
				fragments = append(fragments, "is a protocol implementation")
			}
		default:
			fragments = append(fragments, fmt.Sprintf("is a %s", strings.ReplaceAll(moduleKind, "_", " ")))
		}
	}
	if attributeKind, _ := metadata["attribute_kind"].(string); attributeKind != "" {
		fragments = append(fragments, fmt.Sprintf("is a %s", strings.ReplaceAll(attributeKind, "_", " ")))
	}

	if len(fragments) == 0 {
		return ""
	}
	if len(fragments) == 1 {
		return fmt.Sprintf("%s %s %s.", label, name, fragments[0])
	}
	return fmt.Sprintf("%s %s %s.", label, name, joinSentenceFragments(fragments))
}

func attachSemanticSummary(result map[string]any) {
	if result == nil {
		return
	}
	metadata, _ := result["metadata"].(map[string]any)
	if len(metadata) == 0 {
		return
	}

	entity := map[string]any{
		"metadata": metadata,
	}
	if name := StringVal(result, "name"); name != "" {
		entity["name"] = name
	} else if name := StringVal(result, "entity_name"); name != "" {
		entity["name"] = name
	}
	if labels := StringSliceVal(result, "labels"); len(labels) > 0 {
		entity["labels"] = labels
	} else if entityType := StringVal(result, "entity_type"); entityType != "" {
		entity["labels"] = []string{entityType}
	}

	if summary := buildEntitySemanticSummary(entity); summary != "" {
		result["semantic_summary"] = summary
	}
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

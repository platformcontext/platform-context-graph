package query

// buildEntitySemanticProfile promotes the highest-signal structured semantics
// already present in parser metadata into a stable query-surface bundle.
func buildEntitySemanticProfile(entity map[string]any) map[string]any {
	metadata, _ := entity["metadata"].(map[string]any)
	if len(metadata) == 0 {
		return nil
	}

	label := primaryEntityLabel(entity)
	language := StringVal(entity, "language")

	profile := map[string]any{}
	signals := make([]string, 0, 6)

	decorators := metadataStringSlice(metadata, "decorators")
	if len(decorators) > 0 {
		profile["decorators"] = decorators
		signals = append(signals, "decorators")
	}

	if async := boolValue(metadata["async"]); async {
		profile["async"] = true
		signals = append(signals, "async")
	}

	typeParameters := metadataStringSlice(metadata, "type_parameters")
	if len(typeParameters) > 0 {
		profile["type_parameters"] = typeParameters
		signals = append(signals, "type_parameters")
	}

	jsSemantics := ExtractJavaScriptSemantics(metadata)
	if jsSemantics.MethodKind != "" {
		profile["method_kind"] = jsSemantics.MethodKind
		signals = append(signals, "method_kind")
	}
	if jsSemantics.Docstring != "" {
		profile["docstring"] = jsSemantics.Docstring
		signals = append(signals, "docstring")
	}

	if framework, ok := metadata["framework"].(string); ok && framework != "" {
		profile["framework"] = framework
		signals = append(signals, "framework")
	}

	if label == "Annotation" {
		if kind, _ := metadata["kind"].(string); kind == "applied" {
			profile["annotation"] = true
			signals = append(signals, "annotation")
			if targetKind, _ := metadata["target_kind"].(string); targetKind != "" {
				profile["annotation_target_kind"] = targetKind
			}
		}
	}

	pythonProfile := PythonSemanticProfileFromMetadata(label, metadata)
	if pythonProfile.TypeAnnotation {
		profile["type_annotation"] = true
		signals = append(signals, "type_annotation")
	}

	if len(signals) == 0 {
		return nil
	}

	profile["surface_kind"] = semanticSurfaceKind(label, language, profile, pythonProfile)
	profile["signals"] = signals
	return profile
}

func semanticSurfaceKind(
	label string,
	language string,
	profile map[string]any,
	pythonProfile PythonSemanticProfile,
) string {
	if framework, ok := profile["framework"].(string); ok && framework != "" && label == "Component" {
		return "framework_component"
	}
	if _, ok := profile["annotation"].(bool); ok && label == "Annotation" {
		return "applied_annotation"
	}
	if _, ok := profile["type_annotation"].(bool); ok {
		return "type_annotation"
	}
	if _, ok := profile["type_parameters"].([]string); ok {
		return "generic_declaration"
	}
	if language == "python" && pythonProfile.HasSignals() {
		return pythonProfile.SurfaceKind()
	}
	if _, decorated := profile["decorators"].([]string); decorated {
		if _, async := profile["async"].(bool); async {
			return "decorated_async_entity"
		}
		return "decorated_entity"
	}
	if _, async := profile["async"].(bool); async {
		return "async_function"
	}
	if _, ok := profile["method_kind"].(string); ok {
		return "method"
	}
	if _, ok := profile["docstring"].(string); ok {
		return "documented_entity"
	}
	return "semantic_entity"
}

package query

// graphBackedEntityTypes maps the user-facing entity type name to the Neo4j
// node label used in Cypher queries.
var graphBackedEntityTypes = map[string]string{
	"repository":      "Repository",
	"directory":       "Directory",
	"file":            "File",
	"module":          "Module",
	"function":        "Function",
	"class":           "Class",
	"struct":          "Struct",
	"enum":            "Enum",
	"union":           "Union",
	"macro":           "Macro",
	"variable":        "Variable",
	"type_annotation": "TypeAnnotation",
}

// contentBackedEntityTypes maps user-facing entity types to content-entity
// labels that are already materialized in Postgres but not yet first-class in
// the graph query surface.
var contentBackedEntityTypes = map[string]string{
	"type_alias":              "TypeAlias",
	"type_annotation":         "TypeAnnotation",
	"typedef":                 "Typedef",
	"annotation":              "Annotation",
	"protocol":                "Protocol",
	"impl_block":              "ImplBlock",
	"component":               "Component",
	"terragrunt_dependency":   "TerragruntDependency",
	"terragrunt_local":        "TerragruntLocal",
	"terragrunt_input":        "TerragruntInput",
	"guard":                   "guard",
	"protocol_implementation": "ProtocolImplementation",
}

var graphFirstContentBackedEntityTypes = map[string]string{
	"annotation":              "Annotation",
	"component":               "Component",
	"impl_block":              "ImplBlock",
	"protocol":                "Protocol",
	"protocol_implementation": "ProtocolImplementation",
	"module_attribute":        "Variable",
	"type_alias":              "TypeAlias",
	"typedef":                 "Typedef",
}

// buildLanguageResult converts a Neo4j result row into the response shape.
func buildLanguageResult(row map[string]any, label string) map[string]any {
	result := map[string]any{
		"entity_id": StringVal(row, "entity_id"),
		"name":      StringVal(row, "name"),
	}

	if v := StringSliceVal(row, "labels"); v != nil {
		result["labels"] = v
	}
	if v := StringVal(row, "file_path"); v != "" {
		result["file_path"] = v
	}
	if v := StringVal(row, "repo_id"); v != "" {
		result["repo_id"] = v
	}
	if v := StringVal(row, "repo_name"); v != "" {
		result["repo_name"] = v
	}
	if v := StringVal(row, "language"); v != "" {
		result["language"] = v
	}

	switch label {
	case "Repository":
		result["id"] = StringVal(row, "id")
		result["name"] = StringVal(row, "name")
		result["local_path"] = StringVal(row, "local_path")
		result["remote_url"] = StringVal(row, "remote_url")
		result["file_count"] = IntVal(row, "file_count")
	case "Directory":
		result["file_count"] = IntVal(row, "file_count")
	default:
		if v := IntVal(row, "start_line"); v != 0 {
			result["start_line"] = v
		}
		if v := IntVal(row, "end_line"); v != 0 {
			result["end_line"] = v
		}
		if metadata := graphResultMetadata(row); len(metadata) > 0 {
			result["metadata"] = metadata
			attachSemanticSummary(result)
		}
	}

	return result
}

func graphResultMetadata(row map[string]any) map[string]any {
	metadata := map[string]any{}
	if v := StringVal(row, "docstring"); v != "" {
		metadata["docstring"] = v
	}
	if v := StringVal(row, "method_kind"); v != "" {
		metadata["method_kind"] = v
	}
	if v := StringVal(row, "annotation_kind"); v != "" {
		metadata["annotation_kind"] = v
	}
	if v := StringVal(row, "context"); v != "" {
		metadata["context"] = v
	}
	if v := IntVal(row, "type_annotation_count"); v > 0 {
		metadata["type_annotation_count"] = v
	}
	if values := StringSliceVal(row, "type_annotation_kinds"); len(values) > 0 {
		typeAnnotationKinds := make([]any, 0, len(values))
		for _, value := range values {
			typeAnnotationKinds = append(typeAnnotationKinds, value)
		}
		metadata["type_annotation_kinds"] = typeAnnotationKinds
	}
	if values := StringSliceVal(row, "type_parameters"); len(values) > 0 {
		typeParameters := make([]any, 0, len(values))
		for _, value := range values {
			typeParameters = append(typeParameters, value)
		}
		metadata["type_parameters"] = typeParameters
	}
	if v := StringVal(row, "type_alias_kind"); v != "" {
		metadata["type_alias_kind"] = v
	}
	if v := StringVal(row, "framework"); v != "" {
		metadata["framework"] = v
	}
	if v := StringVal(row, "module_kind"); v != "" {
		metadata["module_kind"] = v
	}
	if v, ok := row["jsx_fragment_shorthand"].(bool); ok {
		metadata["jsx_fragment_shorthand"] = v
	}
	if v := StringVal(row, "component_type_assertion"); v != "" {
		metadata["component_type_assertion"] = v
	}
	if v := StringVal(row, "component_wrapper_kind"); v != "" {
		metadata["component_wrapper_kind"] = v
	}
	if v := StringVal(row, "protocol"); v != "" {
		metadata["protocol"] = v
	}
	if v := StringVal(row, "implemented_for"); v != "" {
		metadata["implemented_for"] = v
	}
	if v := StringVal(row, "attribute_kind"); v != "" {
		metadata["attribute_kind"] = v
	}
	if v := StringVal(row, "value"); v != "" {
		metadata["value"] = v
	}
	if v := StringVal(row, "declaration_merge_group"); v != "" {
		metadata["declaration_merge_group"] = v
	}
	if v := IntVal(row, "declaration_merge_count"); v > 0 {
		metadata["declaration_merge_count"] = v
	}
	if values := StringSliceVal(row, "declaration_merge_kinds"); len(values) > 0 {
		declarationMergeKinds := make([]any, 0, len(values))
		for _, value := range values {
			declarationMergeKinds = append(declarationMergeKinds, value)
		}
		metadata["declaration_merge_kinds"] = declarationMergeKinds
	}
	if v := StringVal(row, "kind"); v != "" {
		metadata["kind"] = v
	}
	if v := StringVal(row, "target_kind"); v != "" {
		metadata["target_kind"] = v
	}
	if v := StringVal(row, "type"); v != "" {
		metadata["type"] = v
	}
	if values := StringSliceVal(row, "decorators"); len(values) > 0 {
		decorators := make([]any, 0, len(values))
		for _, value := range values {
			decorators = append(decorators, value)
		}
		metadata["decorators"] = decorators
	}
	if v, ok := row["async"].(bool); ok {
		metadata["async"] = v
	}
	if v := StringVal(row, "semantic_kind"); v != "" {
		metadata["semantic_kind"] = v
	}
	if v := StringVal(row, "metaclass"); v != "" {
		metadata["metaclass"] = v
	}
	if len(metadata) == 0 {
		return nil
	}
	return metadata
}

func graphSemanticMetadataProjection() string {
	return `,
		       e.docstring as docstring,
		       e.method_kind as method_kind,
		       e.annotation_kind as annotation_kind,
		       e.context as context,
		       e.type_annotation_count as type_annotation_count,
		       e.type_annotation_kinds as type_annotation_kinds,
		       e.type_parameters as type_parameters,
		       e.type_alias_kind as type_alias_kind,
		       e.framework as framework,
		       e.module_kind as module_kind,
		       e.jsx_fragment_shorthand as jsx_fragment_shorthand,
		       e.component_type_assertion as component_type_assertion,
		       e.component_wrapper_kind as component_wrapper_kind,
		       e.protocol as protocol,
		       e.implemented_for as implemented_for,
		       e.attribute_kind as attribute_kind,
		       e.value as value,
		       e.declaration_merge_group as declaration_merge_group,
		       e.declaration_merge_count as declaration_merge_count,
		       e.declaration_merge_kinds as declaration_merge_kinds,
		       e.kind as kind,
		       e.target_kind as target_kind,
		       e.type as type,
		       e.decorators as decorators,
		       e.async as async,
		       e.semantic_kind as semantic_kind,
		       e.metaclass as metaclass`
}

func graphLabelToContentEntityType(label string) string {
	switch label {
	case "Annotation":
		return "Annotation"
	case "Function", "Class", "Module", "Variable", "Struct", "Enum", "Union", "Macro", "ImplBlock", "Typedef", "TypeAlias", "TypeAnnotation", "Component":
		return label
	default:
		return ""
	}
}

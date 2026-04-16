package query

func buildOutgoingTerraformRelationships(entity EntityContent) ([]map[string]any, bool, error) {
	switch entity.EntityType {
	case "TerraformModule":
		if source, ok := metadataNonEmptyString(entity.Metadata, "source"); ok {
			return []map[string]any{
				{
					"type":        "DEPLOYS_FROM",
					"target_name": source,
					"reason":      "terraform_module_source",
				},
			}, true, nil
		}
		return nil, true, nil
	case "TerragruntConfig":
		if source, ok := metadataNonEmptyString(entity.Metadata, "terraform_source"); ok {
			return []map[string]any{
				{
					"type":        "DEPLOYS_FROM",
					"target_name": source,
					"reason":      "terragrunt_terraform_source",
				},
			}, true, nil
		}
		return nil, true, nil
	case "TerragruntDependency":
		if configPath, ok := metadataNonEmptyString(entity.Metadata, "config_path"); ok {
			return []map[string]any{
				{
					"type":        "DEPENDS_ON",
					"target_name": configPath,
					"reason":      "terragrunt_dependency_config_path",
				},
			}, true, nil
		}
		return nil, true, nil
	default:
		return nil, false, nil
	}
}

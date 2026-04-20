package query

import (
	"context"
	"sort"
)

const repositoryInfrastructureEntityLimit = 5000

func queryRepoInfrastructureRows(
	ctx context.Context,
	reader GraphReader,
	content *ContentReader,
	params map[string]any,
) []map[string]any {
	result := queryRepoInfrastructureFromGraph(ctx, reader, params)
	if content == nil {
		return result
	}

	repoID := StringVal(params, "repo_id")
	if repoID == "" {
		return result
	}

	entities, err := content.ListRepoEntities(ctx, repoID, repositoryInfrastructureEntityLimit)
	if err != nil || len(entities) == 0 {
		return result
	}

	seen := make(map[string]struct{}, len(result))
	for _, row := range result {
		seen[repositoryInfrastructureEntryKey(row)] = struct{}{}
	}

	for _, entity := range entities {
		entry, ok := repositoryInfrastructureEntryFromContent(entity)
		if !ok {
			continue
		}
		key := repositoryInfrastructureEntryKey(entry)
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		result = append(result, entry)
	}

	sort.SliceStable(result, func(i, j int) bool {
		leftType := StringVal(result[i], "type")
		rightType := StringVal(result[j], "type")
		if leftType != rightType {
			return leftType < rightType
		}
		leftName := StringVal(result[i], "name")
		rightName := StringVal(result[j], "name")
		if leftName != rightName {
			return leftName < rightName
		}
		return StringVal(result[i], "file_path") < StringVal(result[j], "file_path")
	})

	return result
}

func queryRepoInfrastructureFromGraph(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (r:Repository {id: $repo_id})-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(infra)
		WHERE infra:K8sResource OR infra:TerraformResource OR infra:TerraformModule
		      OR infra:TerragruntConfig OR infra:TerragruntDependency
		      OR infra:ArgoCDApplication OR infra:ArgoCDApplicationSet
		      OR infra:HelmChart OR infra:HelmValues
		      OR infra:KustomizeOverlay
		      OR infra:CrossplaneXRD OR infra:CrossplaneComposition OR infra:CrossplaneClaim
		      OR infra:CloudFormationResource
		RETURN labels(infra)[0] AS type, infra.name AS name,
		       infra.kind AS kind, infra.source AS source,
		       infra.terraform_source AS terraform_source,
		       infra.config_path AS config_path,
		       f.relative_path AS file_path
		ORDER BY type, name
	`, params)
	if err != nil || len(rows) == 0 {
		return make([]map[string]any, 0)
	}

	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		result = append(result, repositoryInfrastructureEntryFromRow(row))
	}
	return result
}

func repositoryInfrastructureEntryFromRow(row map[string]any) map[string]any {
	entry := map[string]any{
		"type":      StringVal(row, "type"),
		"name":      StringVal(row, "name"),
		"file_path": StringVal(row, "file_path"),
	}
	if kind := StringVal(row, "kind"); kind != "" {
		entry["kind"] = kind
	}
	if source := StringVal(row, "source"); source != "" {
		entry["source"] = source
	}
	if terraformSource := StringVal(row, "terraform_source"); terraformSource != "" {
		entry["terraform_source"] = terraformSource
	}
	if configPath := StringVal(row, "config_path"); configPath != "" {
		entry["config_path"] = configPath
	}
	return entry
}

func repositoryInfrastructureEntryFromContent(entity EntityContent) (map[string]any, bool) {
	entry := map[string]any{
		"type":      entity.EntityType,
		"name":      entity.EntityName,
		"file_path": entity.RelativePath,
	}
	switch entity.EntityType {
	case "TerraformModule":
		if source, ok := metadataNonEmptyString(entity.Metadata, "source"); ok {
			entry["source"] = source
		}
		if deploymentName, ok := metadataNonEmptyString(entity.Metadata, "deployment_name"); ok {
			entry["deployment_name"] = deploymentName
		}
	case "TerragruntConfig":
		if terraformSource, ok := metadataNonEmptyString(entity.Metadata, "terraform_source"); ok {
			entry["terraform_source"] = terraformSource
			entry["source"] = terraformSource
		}
		if includes := metadataStringSlice(entity.Metadata, "includes"); len(includes) > 0 {
			entry["includes"] = includes
		}
		if inputs := metadataStringSlice(entity.Metadata, "inputs"); len(inputs) > 0 {
			entry["inputs"] = inputs
		}
		if locals := metadataStringSlice(entity.Metadata, "locals"); len(locals) > 0 {
			entry["locals"] = locals
		}
	case "TerragruntDependency":
		if configPath, ok := metadataNonEmptyString(entity.Metadata, "config_path"); ok {
			entry["config_path"] = configPath
		}
	case "ArgoCDApplication", "ArgoCDApplicationSet", "KustomizeOverlay", "HelmChart",
		"HelmValues", "CrossplaneXRD", "CrossplaneComposition", "CrossplaneClaim",
		"CloudFormationResource", "K8sResource", "TerraformResource":
		if source, ok := metadataNonEmptyString(entity.Metadata, "source"); ok {
			entry["source"] = source
		}
		if kind, ok := metadataNonEmptyString(entity.Metadata, "kind"); ok {
			entry["kind"] = kind
		}
	default:
		return nil, false
	}
	return entry, true
}

func repositoryInfrastructureEntryKey(entry map[string]any) string {
	return StringVal(entry, "type") + "|" + StringVal(entry, "name") + "|" + StringVal(entry, "file_path")
}

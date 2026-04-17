package query

import (
	"context"
	"testing"
)

func TestBuildContentRelationshipSetTerragruntConfigPromotesHelperPaths(t *testing.T) {
	t.Parallel()

	relationships, err := buildContentRelationshipSet(context.Background(), nil, EntityContent{
		EntityID:   "tg-config-helpers-1",
		RepoID:     "repo-1",
		EntityType: "TerragruntConfig",
		EntityName: "terragrunt",
		Metadata: map[string]any{
			"include_paths":                "root.hcl",
			"read_config_paths":            "env.hcl",
			"find_in_parent_folders_paths": "env.hcl,root.hcl",
			"local_config_asset_paths":     "config/runtime.yaml,templates/runtime.json",
		},
	})
	if err != nil {
		t.Fatalf("buildContentRelationshipSet() error = %v, want nil", err)
	}

	want := []map[string]string{
		{
			"type":        "DISCOVERS_CONFIG_IN",
			"target_name": "root.hcl",
			"reason":      "terragrunt_include_path",
		},
		{
			"type":        "DISCOVERS_CONFIG_IN",
			"target_name": "env.hcl",
			"reason":      "terragrunt_read_config",
		},
		{
			"type":        "DISCOVERS_CONFIG_IN",
			"target_name": "env.hcl",
			"reason":      "terragrunt_find_in_parent_folders",
		},
		{
			"type":        "DISCOVERS_CONFIG_IN",
			"target_name": "root.hcl",
			"reason":      "terragrunt_find_in_parent_folders",
		},
		{
			"type":        "DISCOVERS_CONFIG_IN",
			"target_name": "config/runtime.yaml",
			"reason":      "local_config_asset",
		},
		{
			"type":        "DISCOVERS_CONFIG_IN",
			"target_name": "templates/runtime.json",
			"reason":      "local_config_asset",
		},
	}

	if len(relationships.outgoing) != len(want) {
		t.Fatalf("len(relationships.outgoing) = %d, want %d", len(relationships.outgoing), len(want))
	}

	gotByKey := make(map[string]map[string]any, len(relationships.outgoing))
	for _, relationship := range relationships.outgoing {
		key := relationship["type"].(string) + "|" + relationship["target_name"].(string) + "|" + relationship["reason"].(string)
		gotByKey[key] = relationship
	}

	for _, expected := range want {
		key := expected["type"] + "|" + expected["target_name"] + "|" + expected["reason"]
		if _, ok := gotByKey[key]; !ok {
			t.Fatalf("missing relationship %q in %#v", key, relationships.outgoing)
		}
	}
}

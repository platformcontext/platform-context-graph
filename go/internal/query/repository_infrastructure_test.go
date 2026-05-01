package query

import "testing"

func TestRepositoryInfrastructureEntryFromContentIncludesTerraformResourceClassification(t *testing.T) {
	t.Parallel()

	entry, ok := repositoryInfrastructureEntryFromContent(EntityContent{
		EntityType:   "TerraformResource",
		EntityName:   "aws_rds_cluster.primary",
		RelativePath: "infra/rds.tf",
		Metadata: map[string]any{
			"provider":          "aws",
			"resource_type":     "aws_rds_cluster",
			"resource_service":  "rds",
			"resource_category": "data",
		},
	})
	if !ok {
		t.Fatal("repositoryInfrastructureEntryFromContent() ok = false, want true")
	}
	for key, want := range map[string]any{
		"provider":          "aws",
		"resource_type":     "aws_rds_cluster",
		"resource_service":  "rds",
		"resource_category": "data",
	} {
		if got := entry[key]; got != want {
			t.Fatalf("entry[%s] = %#v, want %#v", key, got, want)
		}
	}
}

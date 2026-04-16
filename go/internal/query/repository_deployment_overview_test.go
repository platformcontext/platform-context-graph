package query

import "testing"

func TestBuildSharedConfigPathsGroupsDuplicatePathsAcrossRepos(t *testing.T) {
	t.Parallel()

	got := buildSharedConfigPaths(map[string]any{
		"config_paths": []map[string]any{
			{"path": "/configd/payments/*", "source_repo": "helm-charts"},
			{"path": "/configd/payments/*", "source_repo": "terraform-stack-payments"},
			{"path": "/configd/payments/*", "source_repo": "helm-charts"},
			{"path": "/api/payments/*", "source_repo": "helm-charts"},
		},
	})

	if len(got) != 1 {
		t.Fatalf("len(shared_config_paths) = %d, want 1", len(got))
	}
	if got[0]["path"] != "/configd/payments/*" {
		t.Fatalf("shared_config_paths[0].path = %#v, want %q", got[0]["path"], "/configd/payments/*")
	}
	sourceRepos, ok := got[0]["source_repositories"].([]string)
	if !ok {
		t.Fatalf("source_repositories type = %T, want []string", got[0]["source_repositories"])
	}
	if len(sourceRepos) != 2 {
		t.Fatalf("len(source_repositories) = %d, want 2", len(sourceRepos))
	}
	if sourceRepos[0] != "helm-charts" || sourceRepos[1] != "terraform-stack-payments" {
		t.Fatalf("source_repositories = %#v, want sorted unique repos", sourceRepos)
	}
}

func TestBuildSharedConfigPathsOmitsBlankAndSingleSourceRows(t *testing.T) {
	t.Parallel()

	got := buildSharedConfigPaths(map[string]any{
		"config_paths": []map[string]any{
			{"path": "", "source_repo": "helm-charts"},
			{"path": "/configd/payments/*", "source_repo": ""},
			{"path": "/configd/payments/*", "source_repo": "helm-charts"},
		},
	})

	if len(got) != 0 {
		t.Fatalf("shared_config_paths = %#v, want empty", got)
	}
}

func TestBuildTopologyStoryIncludesSharedConfigLine(t *testing.T) {
	t.Parallel()

	got := buildTopologyStory([]map[string]any{
		{
			"path":                "/configd/payments/*",
			"source_repositories": []string{"helm-charts", "terraform-stack-payments"},
		},
	})

	if len(got) != 1 {
		t.Fatalf("len(topology_story) = %d, want 1", len(got))
	}
	want := "Shared config families span /configd/payments/* across helm-charts, terraform-stack-payments."
	if got[0] != want {
		t.Fatalf("topology_story[0] = %q, want %q", got[0], want)
	}
}

package query

import "testing"

func TestBuildRepositorySemanticOverviewCountsSemanticSignals(t *testing.T) {
	t.Parallel()

	overview := buildRepositorySemanticOverview([]EntityContent{
		{
			EntityID:   "fn-1",
			RepoID:     "repo-1",
			EntityType: "Function",
			EntityName: "handler",
			Language:   "python",
			Metadata: map[string]any{
				"decorators": []any{"@route"},
				"async":      true,
			},
		},
		{
			EntityID:   "cls-1",
			RepoID:     "repo-1",
			EntityType: "Class",
			EntityName: "Demo",
			Language:   "typescript",
			Metadata: map[string]any{
				"decorators":      []any{"@sealed"},
				"type_parameters": []any{"T"},
			},
		},
		{
			EntityID:   "cmp-1",
			RepoID:     "repo-1",
			EntityType: "Component",
			EntityName: "Button",
			Language:   "tsx",
			Metadata: map[string]any{
				"framework": "react",
			},
		},
		{
			EntityID:   "annotation-1",
			RepoID:     "repo-1",
			EntityType: "Annotation",
			EntityName: "Logged",
			Language:   "java",
			Metadata: map[string]any{
				"kind":        "applied",
				"target_kind": "method_declaration",
			},
		},
	})

	if overview == nil {
		t.Fatal("buildRepositorySemanticOverview() = nil, want non-nil")
	}
	if got, want := overview["entity_count"], 4; got != want {
		t.Fatalf("entity_count = %#v, want %#v", got, want)
	}

	languageCounts, ok := overview["language_counts"].(map[string]int)
	if !ok {
		t.Fatalf("language_counts type = %T, want map[string]int", overview["language_counts"])
	}
	if got, want := languageCounts["python"], 1; got != want {
		t.Fatalf("language_counts[python] = %d, want %d", got, want)
	}
	if got, want := languageCounts["typescript"], 1; got != want {
		t.Fatalf("language_counts[typescript] = %d, want %d", got, want)
	}
	if got, want := languageCounts["tsx"], 1; got != want {
		t.Fatalf("language_counts[tsx] = %d, want %d", got, want)
	}
	if got, want := languageCounts["java"], 1; got != want {
		t.Fatalf("language_counts[java] = %d, want %d", got, want)
	}

	signalCounts, ok := overview["signal_counts"].(map[string]int)
	if !ok {
		t.Fatalf("signal_counts type = %T, want map[string]int", overview["signal_counts"])
	}
	if got, want := signalCounts["decorators"], 2; got != want {
		t.Fatalf("signal_counts[decorators] = %d, want %d", got, want)
	}
	if got, want := signalCounts["async"], 1; got != want {
		t.Fatalf("signal_counts[async] = %d, want %d", got, want)
	}
	if got, want := signalCounts["type_parameters"], 1; got != want {
		t.Fatalf("signal_counts[type_parameters] = %d, want %d", got, want)
	}
	if got, want := signalCounts["framework"], 1; got != want {
		t.Fatalf("signal_counts[framework] = %d, want %d", got, want)
	}
	if got, want := signalCounts["annotation"], 1; got != want {
		t.Fatalf("signal_counts[annotation] = %d, want %d", got, want)
	}

	surfaceKinds, ok := overview["surface_kind_counts"].(map[string]int)
	if !ok {
		t.Fatalf("surface_kind_counts type = %T, want map[string]int", overview["surface_kind_counts"])
	}
	if got, want := surfaceKinds["decorated_async_function"], 1; got != want {
		t.Fatalf("surface_kind_counts[decorated_async_function] = %d, want %d", got, want)
	}
	if got, want := surfaceKinds["generic_declaration"], 1; got != want {
		t.Fatalf("surface_kind_counts[generic_declaration] = %d, want %d", got, want)
	}
	if got, want := surfaceKinds["framework_component"], 1; got != want {
		t.Fatalf("surface_kind_counts[framework_component] = %d, want %d", got, want)
	}
	if got, want := surfaceKinds["applied_annotation"], 1; got != want {
		t.Fatalf("surface_kind_counts[applied_annotation] = %d, want %d", got, want)
	}
}

func TestBuildRepositoryStoryResponseIncludesSemanticOverview(t *testing.T) {
	t.Parallel()

	repo := RepoRef{ID: "repository:payments", Name: "payments"}
	semanticOverview := map[string]any{
		"entity_count": 3,
		"language_counts": map[string]int{
			"java":       1,
			"python":     1,
			"typescript": 1,
		},
		"signal_counts": map[string]int{
			"annotation": 1,
			"decorators": 1,
			"async":      1,
		},
		"surface_kind_counts": map[string]int{
			"applied_annotation":       1,
			"decorated_async_function": 1,
			"generic_declaration":      1,
		},
	}

	got := buildRepositoryStoryResponse(
		repo,
		42,
		[]string{"python", "typescript"},
		[]string{"payments-api"},
		[]string{"argocd_application"},
		3,
		semanticOverview,
	)

	overview, ok := got["semantic_overview"].(map[string]any)
	if !ok {
		t.Fatalf("semantic_overview type = %T, want map[string]any", got["semantic_overview"])
	}
	if gotValue, want := overview["entity_count"], 3; gotValue != want {
		t.Fatalf("semantic_overview[entity_count] = %#v, want %#v", gotValue, want)
	}

	storySections, ok := got["story_sections"].([]map[string]any)
	if !ok {
		t.Fatalf("story_sections type = %T, want []map[string]any", got["story_sections"])
	}
	if len(storySections) != 4 {
		t.Fatalf("len(story_sections) = %d, want 4", len(storySections))
	}
	if gotValue, want := storySections[2]["title"], "semantics"; gotValue != want {
		t.Fatalf("story_sections[2][title] = %#v, want %#v", gotValue, want)
	}

	if gotValue, want := got["story"], "Repository payments contains 42 indexed files. Languages: python, typescript. Defines 1 workload(s): payments-api. Runs on platform signal(s): argocd_application. Semantic signals cover 3 entity(ies) across 3 language(s): annotation=1, async=1, decorators=1, applied_annotation=1, decorated_async_function=1, and generic_declaration=1."; gotValue != want {
		t.Fatalf("story = %#v, want %#v", gotValue, want)
	}
}

func TestBuildRepositoryStoryResponseOmitsSemanticOverviewWhenEmpty(t *testing.T) {
	t.Parallel()

	repo := RepoRef{ID: "repository:payments", Name: "payments"}
	got := buildRepositoryStoryResponse(
		repo,
		42,
		[]string{"python"},
		nil,
		nil,
		0,
		nil,
	)

	if _, ok := got["semantic_overview"]; ok {
		t.Fatalf("semantic_overview = %#v, want omitted", got["semantic_overview"])
	}
	storySections, ok := got["story_sections"].([]map[string]any)
	if !ok {
		t.Fatalf("story_sections type = %T, want []map[string]any", got["story_sections"])
	}
	if len(storySections) != 3 {
		t.Fatalf("len(story_sections) = %d, want 3", len(storySections))
	}
}

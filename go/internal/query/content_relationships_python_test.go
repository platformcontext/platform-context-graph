package query

import (
	"context"
	"database/sql/driver"
	"testing"
)

func TestBuildContentRelationshipSetPythonClassUsesMetaclass(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"class-meta", "repo-1", "models.py", "Class", "MetaLogger",
					int64(1), int64(2), "python", "class MetaLogger(type): pass", []byte(`{}`),
				},
			},
		},
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{},
		},
	})

	reader := NewContentReader(db)
	entity := EntityContent{
		EntityID:     "class-logged",
		RepoID:       "repo-1",
		RelativePath: "models.py",
		EntityType:   "Class",
		EntityName:   "Logged",
		Language:     "python",
		Metadata: map[string]any{
			"metaclass": "MetaLogger",
		},
	}

	relationships, err := buildContentRelationshipSet(context.Background(), reader, entity)
	if err != nil {
		t.Fatalf("buildContentRelationshipSet() error = %v, want nil", err)
	}
	if len(relationships.outgoing) != 1 {
		t.Fatalf("len(relationships.outgoing) = %d, want 1", len(relationships.outgoing))
	}

	relationship := relationships.outgoing[0]
	if got, want := relationship["type"], "USES_METACLASS"; got != want {
		t.Fatalf("relationship[type] = %#v, want %#v", got, want)
	}
	if got, want := relationship["target_name"], "MetaLogger"; got != want {
		t.Fatalf("relationship[target_name] = %#v, want %#v", got, want)
	}
	if got, want := relationship["target_id"], "class-meta"; got != want {
		t.Fatalf("relationship[target_id] = %#v, want %#v", got, want)
	}
	if got, want := relationship["reason"], "python_metaclass"; got != want {
		t.Fatalf("relationship[reason] = %#v, want %#v", got, want)
	}
}

func TestBuildContentRelationshipSetPythonMetaclassHasIncomingUsage(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"class-logged", "repo-1", "models.py", "Class", "Logged",
					int64(4), int64(5), "python", "class Logged(metaclass=MetaLogger): pass", []byte(`{"metaclass":"MetaLogger"}`),
				},
			},
		},
	})

	reader := NewContentReader(db)
	entity := EntityContent{
		EntityID:     "class-meta",
		RepoID:       "repo-1",
		RelativePath: "models.py",
		EntityType:   "Class",
		EntityName:   "MetaLogger",
		Language:     "python",
		Metadata:     map[string]any{},
	}

	relationships, err := buildContentRelationshipSet(context.Background(), reader, entity)
	if err != nil {
		t.Fatalf("buildContentRelationshipSet() error = %v, want nil", err)
	}
	if len(relationships.incoming) != 1 {
		t.Fatalf("len(relationships.incoming) = %d, want 1", len(relationships.incoming))
	}

	relationship := relationships.incoming[0]
	if got, want := relationship["type"], "USES_METACLASS"; got != want {
		t.Fatalf("relationship[type] = %#v, want %#v", got, want)
	}
	if got, want := relationship["source_name"], "Logged"; got != want {
		t.Fatalf("relationship[source_name] = %#v, want %#v", got, want)
	}
	if got, want := relationship["source_id"], "class-logged"; got != want {
		t.Fatalf("relationship[source_id] = %#v, want %#v", got, want)
	}
	if got, want := relationship["reason"], "python_metaclass"; got != want {
		t.Fatalf("relationship[reason] = %#v, want %#v", got, want)
	}
}

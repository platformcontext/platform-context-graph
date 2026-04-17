package reducer

import "testing"

func TestGraphProjectionPhaseKeyValidate(t *testing.T) {
	t.Parallel()

	key := GraphProjectionPhaseKey{
		ScopeID:          "scope-a",
		AcceptanceUnitID: "repo-a",
		SourceRunID:      "run-1",
		GenerationID:     "gen-1",
		Keyspace:         GraphProjectionKeyspaceCodeEntitiesUID,
	}
	if err := key.Validate(); err != nil {
		t.Fatalf("Validate() error = %v, want nil", err)
	}
}

func TestGraphProjectionPhaseKeyValidateRejectsBlankFields(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		key  GraphProjectionPhaseKey
	}{
		{
			name: "blank scope",
			key: GraphProjectionPhaseKey{
				AcceptanceUnitID: "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Keyspace:         GraphProjectionKeyspaceCodeEntitiesUID,
			},
		},
		{
			name: "blank acceptance unit",
			key: GraphProjectionPhaseKey{
				ScopeID:      "scope-a",
				SourceRunID:  "run-1",
				GenerationID: "gen-1",
				Keyspace:     GraphProjectionKeyspaceCodeEntitiesUID,
			},
		},
		{
			name: "blank source run",
			key: GraphProjectionPhaseKey{
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				GenerationID:     "gen-1",
				Keyspace:         GraphProjectionKeyspaceCodeEntitiesUID,
			},
		},
		{
			name: "blank generation",
			key: GraphProjectionPhaseKey{
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				SourceRunID:      "run-1",
				Keyspace:         GraphProjectionKeyspaceCodeEntitiesUID,
			},
		},
		{
			name: "blank keyspace",
			key: GraphProjectionPhaseKey{
				ScopeID:          "scope-a",
				AcceptanceUnitID: "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			if err := tt.key.Validate(); err == nil {
				t.Fatal("Validate() error = nil, want non-nil")
			}
		})
	}
}

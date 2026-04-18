package query

import (
	"context"
	"net/http"
	"sort"
)

// CompareHandler provides environment comparison endpoints.
type CompareHandler struct {
	Neo4j GraphReader
}

// Mount registers comparison routes on the given mux.
func (h *CompareHandler) Mount(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v0/compare/environments", h.compareEnvironments)
}

// compareEnvironmentsRequest is the JSON request body.
type compareEnvironmentsRequest struct {
	WorkloadID string `json:"workload_id"`
	Left       string `json:"left"`
	Right      string `json:"right"`
}

// compareEnvironments handles POST /api/v0/compare/environments.
func (h *CompareHandler) compareEnvironments(w http.ResponseWriter, r *http.Request) {
	var req compareEnvironmentsRequest
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.WorkloadID == "" {
		WriteError(w, http.StatusBadRequest, "workload_id is required")
		return
	}
	if req.Left == "" {
		WriteError(w, http.StatusBadRequest, "left environment is required")
		return
	}
	if req.Right == "" {
		WriteError(w, http.StatusBadRequest, "right environment is required")
		return
	}

	ctx := r.Context()

	// Fetch workload
	workload, err := h.fetchWorkload(ctx, req.WorkloadID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// If workload not found, return missing response
	if workload == nil {
		resp := map[string]any{
			"workload": nil,
			"left": map[string]any{
				"environment":     req.Left,
				"status":          "missing",
				"instance":        nil,
				"cloud_resources": []any{},
			},
			"right": map[string]any{
				"environment":     req.Right,
				"status":          "missing",
				"instance":        nil,
				"cloud_resources": []any{},
			},
			"changed": map[string]any{
				"cloud_resources": []any{},
			},
			"confidence": 0.0,
			"reason":     "Workload '" + req.WorkloadID + "' not found",
		}
		WriteJSON(w, http.StatusOK, resp)
		return
	}

	// Fetch environment snapshots
	leftSnap := h.environmentSnapshot(ctx, req.WorkloadID, req.Left)
	rightSnap := h.environmentSnapshot(ctx, req.WorkloadID, req.Right)

	// Compute diff
	leftResources := leftSnap["cloud_resources"].([]map[string]any)
	rightResources := rightSnap["cloud_resources"].([]map[string]any)
	changed := diffCloudResources(leftResources, rightResources, req.Left, req.Right)

	// Compute overall confidence
	confidence, reason := computeConfidence(leftSnap, rightSnap, changed)

	resp := map[string]any{
		"workload": workload,
		"left":     leftSnap,
		"right":    rightSnap,
		"changed": map[string]any{
			"cloud_resources": changed,
		},
		"confidence": confidence,
		"reason":     reason,
	}

	WriteJSON(w, http.StatusOK, resp)
}

// fetchWorkload queries Neo4j for the workload by ID.
func (h *CompareHandler) fetchWorkload(ctx context.Context, workloadID string) (map[string]any, error) {
	cypher := `
		MATCH (w:Workload) WHERE w.id = $workload_id
		RETURN w.id as id, w.name as name, w.kind as kind, w.repo_id as repo_id
	`
	row, err := h.Neo4j.RunSingle(ctx, cypher, map[string]any{"workload_id": workloadID})
	if err != nil {
		return nil, err
	}
	if row == nil {
		return nil, nil
	}
	return map[string]any{
		"id":      StringVal(row, "id"),
		"name":    StringVal(row, "name"),
		"kind":    StringVal(row, "kind"),
		"repo_id": StringVal(row, "repo_id"),
	}, nil
}

// environmentSnapshot fetches the instance and cloud resources for one environment.
func (h *CompareHandler) environmentSnapshot(ctx context.Context, workloadID, environment string) map[string]any {
	// Find the workload instance for this environment
	instanceCypher := `
		MATCH (i:WorkloadInstance)
		WHERE i.workload_id = $workload_id
		  AND i.environment = $environment
		RETURN i.id as id, i.name as name, i.kind as kind,
		       i.environment as environment, i.workload_id as workload_id
		LIMIT 1
	`
	instanceRow, err := h.Neo4j.RunSingle(ctx, instanceCypher, map[string]any{
		"workload_id": workloadID,
		"environment": environment,
	})

	if err != nil || instanceRow == nil {
		return map[string]any{
			"environment":     environment,
			"status":          "unsupported",
			"instance":        nil,
			"cloud_resources": []map[string]any{},
			"reason":          "no materialized workload instance found for environment",
		}
	}

	instance := map[string]any{
		"id":          StringVal(instanceRow, "id"),
		"name":        StringVal(instanceRow, "name"),
		"kind":        StringVal(instanceRow, "kind"),
		"environment": StringVal(instanceRow, "environment"),
		"workload_id": StringVal(instanceRow, "workload_id"),
	}

	// Fetch cloud resources
	resourcesCypher := `
		MATCH (i:WorkloadInstance)-[r:USES]->(c:CloudResource)
		WHERE i.id = $instance_id
		RETURN c.id as id, c.name as name, c.environment as environment,
		       c.kind as kind, c.provider as provider,
		       r.confidence as confidence, r.reason as reason
		ORDER BY c.name
	`
	resourceRows, err := h.Neo4j.Run(ctx, resourcesCypher, map[string]any{
		"instance_id": StringVal(instanceRow, "id"),
	})

	var cloudResources []map[string]any
	if err == nil && resourceRows != nil {
		cloudResources = make([]map[string]any, 0, len(resourceRows))
		for _, row := range resourceRows {
			cloudResources = append(cloudResources, map[string]any{
				"id":          StringVal(row, "id"),
				"name":        StringVal(row, "name"),
				"environment": StringVal(row, "environment"),
				"kind":        StringVal(row, "kind"),
				"provider":    StringVal(row, "provider"),
				"confidence":  floatVal(row, "confidence"),
				"reason":      StringVal(row, "reason"),
			})
		}
	} else {
		cloudResources = []map[string]any{}
	}

	return map[string]any{
		"environment":     environment,
		"status":          "present",
		"instance":        instance,
		"cloud_resources": cloudResources,
	}
}

// diffCloudResources computes added/removed resources between two snapshots.
func diffCloudResources(left, right []map[string]any, leftEnv, rightEnv string) []map[string]any {
	// Build lookup maps by resource ID
	leftMap := make(map[string]map[string]any)
	for _, r := range left {
		leftMap[StringVal(r, "id")] = r
	}

	rightMap := make(map[string]map[string]any)
	for _, r := range right {
		rightMap[StringVal(r, "id")] = r
	}

	changed := make([]map[string]any, 0)

	// Resources in right but not left = added
	for id, r := range rightMap {
		if _, exists := leftMap[id]; !exists {
			changed = append(changed, map[string]any{
				"id":          StringVal(r, "id"),
				"name":        StringVal(r, "name"),
				"kind":        StringVal(r, "kind"),
				"provider":    StringVal(r, "provider"),
				"confidence":  floatVal(r, "confidence"),
				"reason":      StringVal(r, "reason"),
				"change":      "added",
				"environment": rightEnv,
			})
		}
	}

	// Resources in left but not right = removed
	for id, r := range leftMap {
		if _, exists := rightMap[id]; !exists {
			changed = append(changed, map[string]any{
				"id":          StringVal(r, "id"),
				"name":        StringVal(r, "name"),
				"kind":        StringVal(r, "kind"),
				"provider":    StringVal(r, "provider"),
				"confidence":  floatVal(r, "confidence"),
				"reason":      StringVal(r, "reason"),
				"change":      "removed",
				"environment": leftEnv,
			})
		}
	}

	// Sort by confidence descending, then by name
	sort.Slice(changed, func(i, j int) bool {
		confI := floatVal(changed[i], "confidence")
		confJ := floatVal(changed[j], "confidence")
		if confI != confJ {
			return confI > confJ
		}
		return StringVal(changed[i], "name") < StringVal(changed[j], "name")
	})

	return changed
}

// computeConfidence calculates overall confidence and reason for the comparison.
func computeConfidence(left, right map[string]any, changed []map[string]any) (float64, string) {
	leftStatus := StringVal(left, "status")
	rightStatus := StringVal(right, "status")

	// If either environment cannot be materialized, the comparison is not yet
	// supported for this workload/environment pair.
	if leftStatus == "unsupported" || rightStatus == "unsupported" {
		return 0.0, "Comparison unsupported: one or both environments do not have materialized workload instances"
	}
	if leftStatus == "missing" || rightStatus == "missing" {
		return 0.0, "One or both environments not found"
	}

	// If no changes, confidence is 1.0
	if len(changed) == 0 {
		return 1.0, "Environments are identical"
	}

	// Calculate average confidence from changed resources
	var sum float64
	for _, c := range changed {
		sum += floatVal(c, "confidence")
	}
	avgConfidence := sum / float64(len(changed))

	return avgConfidence, "Comparison based on cloud resource differences"
}

// floatVal safely extracts a float64 from a map value.
func floatVal(row map[string]any, key string) float64 {
	v, ok := row[key]
	if !ok || v == nil {
		return 0.0
	}
	switch n := v.(type) {
	case float64:
		return n
	case float32:
		return float64(n)
	case int64:
		return float64(n)
	case int:
		return float64(n)
	default:
		return 0.0
	}
}

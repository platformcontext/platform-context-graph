package status

import (
	"encoding/json"
	"time"

	"slices"
)

// RenderJSON returns a stable machine-readable projection of the report.
func RenderJSON(report Report) ([]byte, error) {
	payload := struct {
		AsOf                  string                     `json:"as_of"`
		Health                HealthSummary              `json:"health"`
		Coordinator           *coordinatorSnapshotJSON   `json:"coordinator,omitempty"`
		Flow                  []flowSummaryJSON          `json:"flow"`
		Queue                 queueJSON                  `json:"queue"`
		RetryPolicies         []retryPolicyJSON          `json:"retry_policies"`
		ScopeActivity         scopeActivityJSON          `json:"scope_activity"`
		GenerationHistory     generationHistoryJSON      `json:"generation_history"`
		GenerationTransitions []generationTransitionJSON `json:"generation_transitions"`
		Scopes                map[string]int             `json:"scopes"`
		Generations           map[string]int             `json:"generations"`
		Stages                []StageSummary             `json:"stages"`
		Domains               []domainBacklogJSON        `json:"domains"`
	}{
		AsOf:                  report.AsOf.UTC().Format(time.RFC3339),
		Health:                report.Health,
		Coordinator:           coordinatorJSON(report.Coordinator),
		Flow:                  flowSummariesJSON(report.FlowSummaries),
		Queue:                 queueJSONFromReport(report.Queue),
		RetryPolicies:         retryPoliciesJSON(report.RetryPolicies),
		ScopeActivity:         scopeActivityJSONFromReport(report.ScopeActivity),
		GenerationHistory:     generationHistoryJSONFromReport(report.GenerationHistory),
		GenerationTransitions: generationTransitionsJSON(report.GenerationTransitions),
		Scopes:                cloneCounts(report.ScopeTotals),
		Generations:           cloneCounts(report.GenerationTotals),
		Stages:                slices.Clone(report.StageSummaries),
		Domains:               domainBacklogsJSON(report.DomainBacklogs),
	}

	return json.MarshalIndent(payload, "", "  ")
}

type queueJSON struct {
	Total                       int     `json:"total"`
	Outstanding                 int     `json:"outstanding"`
	Pending                     int     `json:"pending"`
	InFlight                    int     `json:"in_flight"`
	Retrying                    int     `json:"retrying"`
	Succeeded                   int     `json:"succeeded"`
	Failed                      int     `json:"failed"`
	DeadLetter                  int     `json:"dead_letter"`
	OverdueClaims               int     `json:"overdue_claims"`
	OldestOutstandingAge        string  `json:"oldest_outstanding_age"`
	OldestOutstandingAgeSeconds float64 `json:"oldest_outstanding_age_seconds"`
}

type scopeActivityJSON struct {
	Active    int `json:"active"`
	Changed   int `json:"changed"`
	Unchanged int `json:"unchanged"`
}

type generationHistoryJSON struct {
	Active     int `json:"active"`
	Pending    int `json:"pending"`
	Completed  int `json:"completed"`
	Superseded int `json:"superseded"`
	Failed     int `json:"failed"`
	Other      int `json:"other"`
}

type namedCountJSON struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

type collectorInstanceJSON struct {
	InstanceID     string  `json:"instance_id"`
	CollectorKind  string  `json:"collector_kind"`
	Mode           string  `json:"mode"`
	Enabled        bool    `json:"enabled"`
	Bootstrap      bool    `json:"bootstrap"`
	ClaimsEnabled  bool    `json:"claims_enabled"`
	DisplayName    string  `json:"display_name,omitempty"`
	LastObservedAt string  `json:"last_observed_at"`
	UpdatedAt      string  `json:"updated_at"`
	DeactivatedAt  *string `json:"deactivated_at,omitempty"`
}

type coordinatorSnapshotJSON struct {
	CollectorInstances   []collectorInstanceJSON `json:"collector_instances"`
	RunStatusCounts      []namedCountJSON        `json:"run_status_counts"`
	WorkItemStatusCounts []namedCountJSON        `json:"work_item_status_counts"`
	CompletenessCounts   []namedCountJSON        `json:"completeness_counts"`
	ActiveClaims         int                     `json:"active_claims"`
	OverdueClaims        int                     `json:"overdue_claims"`
	OldestPendingAge     string                  `json:"oldest_pending_age"`
	OldestPendingSeconds float64                 `json:"oldest_pending_age_seconds"`
}

type domainBacklogJSON struct {
	Domain           string  `json:"domain"`
	Outstanding      int     `json:"outstanding"`
	Retrying         int     `json:"retrying"`
	Failed           int     `json:"failed"`
	DeadLetter       int     `json:"dead_letter"`
	OldestAge        string  `json:"oldest_age"`
	OldestAgeSeconds float64 `json:"oldest_age_seconds"`
}

func queueJSONFromReport(queue QueueSnapshot) queueJSON {
	return queueJSON{
		Total:                       queue.Total,
		Outstanding:                 queue.Outstanding,
		Pending:                     queue.Pending,
		InFlight:                    queue.InFlight,
		Retrying:                    queue.Retrying,
		Succeeded:                   queue.Succeeded,
		Failed:                      queue.Failed,
		DeadLetter:                  queue.DeadLetter,
		OverdueClaims:               queue.OverdueClaims,
		OldestOutstandingAge:        queue.OldestOutstandingAge.String(),
		OldestOutstandingAgeSeconds: queue.OldestOutstandingAge.Seconds(),
	}
}

func scopeActivityJSONFromReport(scopeActivity ScopeActivitySnapshot) scopeActivityJSON {
	return scopeActivityJSON(scopeActivity)
}

func domainBacklogsJSON(rows []DomainBacklog) []domainBacklogJSON {
	projected := make([]domainBacklogJSON, 0, len(rows))
	for _, row := range rows {
		projected = append(projected, domainBacklogJSON{
			Domain:           row.Domain,
			Outstanding:      row.Outstanding,
			Retrying:         row.Retrying,
			Failed:           row.Failed,
			DeadLetter:       row.DeadLetter,
			OldestAge:        row.OldestAge.String(),
			OldestAgeSeconds: row.OldestAge.Seconds(),
		})
	}

	return projected
}

func coordinatorJSON(snapshot *CoordinatorSnapshot) *coordinatorSnapshotJSON {
	if snapshot == nil {
		return nil
	}

	instances := make([]collectorInstanceJSON, 0, len(snapshot.CollectorInstances))
	for _, instance := range snapshot.CollectorInstances {
		instances = append(instances, collectorInstanceJSON{
			InstanceID:     instance.InstanceID,
			CollectorKind:  instance.CollectorKind,
			Mode:           instance.Mode,
			Enabled:        instance.Enabled,
			Bootstrap:      instance.Bootstrap,
			ClaimsEnabled:  instance.ClaimsEnabled,
			DisplayName:    instance.DisplayName,
			LastObservedAt: instance.LastObservedAt.UTC().Format(time.RFC3339),
			UpdatedAt:      instance.UpdatedAt.UTC().Format(time.RFC3339),
			DeactivatedAt:  nullableRFC3339String(instance.DeactivatedAt),
		})
	}

	return &coordinatorSnapshotJSON{
		CollectorInstances:   instances,
		RunStatusCounts:      namedCountsJSON(snapshot.RunStatusCounts),
		WorkItemStatusCounts: namedCountsJSON(snapshot.WorkItemStatusCounts),
		CompletenessCounts:   namedCountsJSON(snapshot.CompletenessCounts),
		ActiveClaims:         snapshot.ActiveClaims,
		OverdueClaims:        snapshot.OverdueClaims,
		OldestPendingAge:     snapshot.OldestPendingAge.String(),
		OldestPendingSeconds: snapshot.OldestPendingAge.Seconds(),
	}
}

func namedCountsJSON(rows []NamedCount) []namedCountJSON {
	projected := make([]namedCountJSON, 0, len(rows))
	for _, row := range rows {
		projected = append(projected, namedCountJSON{
			Name:  row.Name,
			Count: row.Count,
		})
	}
	return projected
}

func nullableRFC3339String(value time.Time) *string {
	if value.IsZero() {
		return nil
	}
	formatted := value.UTC().Format(time.RFC3339)
	return &formatted
}

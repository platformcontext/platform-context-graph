package status

import (
	"encoding/json"
	"time"

	"slices"
)

// RenderJSON returns a stable machine-readable projection of the report.
func RenderJSON(report Report) ([]byte, error) {
	payload := struct {
		AsOf              string                `json:"as_of"`
		Health            HealthSummary         `json:"health"`
		Flow              []flowSummaryJSON     `json:"flow"`
		Queue             queueJSON             `json:"queue"`
		RetryPolicies     []retryPolicyJSON     `json:"retry_policies"`
		ScopeActivity     scopeActivityJSON     `json:"scope_activity"`
		GenerationHistory generationHistoryJSON `json:"generation_history"`
		Scopes            map[string]int        `json:"scopes"`
		Generations       map[string]int        `json:"generations"`
		Stages            []StageSummary        `json:"stages"`
		Domains           []domainBacklogJSON   `json:"domains"`
	}{
		AsOf:              report.AsOf.UTC().Format(time.RFC3339),
		Health:            report.Health,
		Flow:              flowSummariesJSON(report.FlowSummaries),
		Queue:             queueJSONFromReport(report.Queue),
		RetryPolicies:     retryPoliciesJSON(report.RetryPolicies),
		ScopeActivity:     scopeActivityJSONFromReport(report.ScopeActivity),
		GenerationHistory: generationHistoryJSONFromReport(report.GenerationHistory),
		Scopes:            cloneCounts(report.ScopeTotals),
		Generations:       cloneCounts(report.GenerationTotals),
		Stages:            slices.Clone(report.StageSummaries),
		Domains:           domainBacklogsJSON(report.DomainBacklogs),
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

type domainBacklogJSON struct {
	Domain           string  `json:"domain"`
	Outstanding      int     `json:"outstanding"`
	Retrying         int     `json:"retrying"`
	Failed           int     `json:"failed"`
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
		OverdueClaims:               queue.OverdueClaims,
		OldestOutstandingAge:        queue.OldestOutstandingAge.String(),
		OldestOutstandingAgeSeconds: queue.OldestOutstandingAge.Seconds(),
	}
}

func scopeActivityJSONFromReport(scopeActivity ScopeActivitySnapshot) scopeActivityJSON {
	return scopeActivityJSON{
		Active:    scopeActivity.Active,
		Changed:   scopeActivity.Changed,
		Unchanged: scopeActivity.Unchanged,
	}
}

func domainBacklogsJSON(rows []DomainBacklog) []domainBacklogJSON {
	projected := make([]domainBacklogJSON, 0, len(rows))
	for _, row := range rows {
		projected = append(projected, domainBacklogJSON{
			Domain:           row.Domain,
			Outstanding:      row.Outstanding,
			Retrying:         row.Retrying,
			Failed:           row.Failed,
			OldestAge:        row.OldestAge.String(),
			OldestAgeSeconds: row.OldestAge.Seconds(),
		})
	}

	return projected
}

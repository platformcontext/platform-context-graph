// Package status projects raw Go data-plane runtime counts into an
// operator-facing status report.
package status

import (
	"encoding/json"
	"fmt"
	"slices"
	"sort"
	"strings"
	"time"
)

const (
	healthHealthy     = "healthy"
	healthProgressing = "progressing"
	healthDegraded    = "degraded"
	healthStalled     = "stalled"
)

// NamedCount captures one status bucket and its count.
type NamedCount struct {
	Name  string
	Count int
}

// StageStatusCount captures one stage/status bucket from the work queue.
type StageStatusCount struct {
	Stage  string
	Status string
	Count  int
}

// QueueSnapshot captures aggregate queue pressure and progress signals.
type QueueSnapshot struct {
	Total                int
	Outstanding          int
	Pending              int
	InFlight             int
	Retrying             int
	Succeeded            int
	Failed               int
	OldestOutstandingAge time.Duration
	OverdueClaims        int
}

// DomainBacklog captures backlog depth for one reducer or projection domain.
type DomainBacklog struct {
	Domain      string
	Outstanding int
	Retrying    int
	Failed      int
	OldestAge   time.Duration
}

// RawSnapshot is the read-only substrate snapshot gathered from Postgres.
type RawSnapshot struct {
	AsOf             time.Time
	ScopeCounts      []NamedCount
	GenerationCounts []NamedCount
	StageCounts      []StageStatusCount
	DomainBacklogs   []DomainBacklog
	Queue            QueueSnapshot
}

// Options controls operator-health projection behavior.
type Options struct {
	StallAfter  time.Duration
	DomainLimit int
}

// HealthSummary captures the operator-facing health verdict and reasons.
type HealthSummary struct {
	State   string
	Reasons []string
}

// StageSummary collapses queue counts into one row per stage.
type StageSummary struct {
	Stage     string
	Pending   int
	Claimed   int
	Running   int
	Retrying  int
	Succeeded int
	Failed    int
}

// Report is the operator-facing summary rendered by CLI and future admin APIs.
type Report struct {
	AsOf             time.Time
	Health           HealthSummary
	Queue            QueueSnapshot
	ScopeTotals      map[string]int
	GenerationTotals map[string]int
	StageSummaries   []StageSummary
	DomainBacklogs   []DomainBacklog
}

// DefaultOptions returns the baseline operator heuristics for this first live
// status surface.
func DefaultOptions() Options {
	return Options{
		StallAfter:  10 * time.Minute,
		DomainLimit: 5,
	}
}

// BuildReport projects one raw substrate snapshot into an operator-facing
// report.
func BuildReport(raw RawSnapshot, opts Options) Report {
	if opts.StallAfter <= 0 {
		opts.StallAfter = DefaultOptions().StallAfter
	}
	if opts.DomainLimit <= 0 {
		opts.DomainLimit = DefaultOptions().DomainLimit
	}

	scopeTotals := toCountMap(raw.ScopeCounts)
	generationTotals := toCountMap(raw.GenerationCounts)
	stageSummaries := summarizeStages(raw.StageCounts)
	domainBacklogs := topDomainBacklogs(raw.DomainBacklogs, opts.DomainLimit)

	return Report{
		AsOf:             raw.AsOf,
		Health:           evaluateHealth(raw.Queue, generationTotals, opts),
		Queue:            raw.Queue,
		ScopeTotals:      scopeTotals,
		GenerationTotals: generationTotals,
		StageSummaries:   stageSummaries,
		DomainBacklogs:   domainBacklogs,
	}
}

// RenderText returns a compact admin-panel-style text summary.
func RenderText(report Report) string {
	lines := []string{
		fmt.Sprintf("Health: %s", report.Health.State),
		fmt.Sprintf(
			"Queue: outstanding=%d in_flight=%d retrying=%d failed=%d oldest=%s overdue_claims=%d",
			report.Queue.Outstanding,
			report.Queue.InFlight,
			report.Queue.Retrying,
			report.Queue.Failed,
			report.Queue.OldestOutstandingAge,
			report.Queue.OverdueClaims,
		),
		fmt.Sprintf("Scopes: %s", formatNamedTotals(report.ScopeTotals)),
		fmt.Sprintf("Generations: %s", formatNamedTotals(report.GenerationTotals)),
	}

	if len(report.Health.Reasons) > 0 {
		lines = append(lines, fmt.Sprintf("Reasons: %s", strings.Join(report.Health.Reasons, "; ")))
	}
	if len(report.StageSummaries) > 0 {
		lines = append(lines, "Stages:")
		for _, row := range report.StageSummaries {
			lines = append(
				lines,
				fmt.Sprintf(
					"  %s pending=%d claimed=%d running=%d retrying=%d succeeded=%d failed=%d",
					row.Stage,
					row.Pending,
					row.Claimed,
					row.Running,
					row.Retrying,
					row.Succeeded,
					row.Failed,
				),
			)
		}
	}
	if len(report.DomainBacklogs) > 0 {
		lines = append(lines, "Domains:")
		for _, row := range report.DomainBacklogs {
			lines = append(
				lines,
				fmt.Sprintf(
					"  %s outstanding=%d retrying=%d failed=%d oldest=%s",
					row.Domain,
					row.Outstanding,
					row.Retrying,
					row.Failed,
					row.OldestAge,
				),
			)
		}
	}

	return strings.Join(lines, "\n")
}

// RenderJSON returns a stable machine-readable projection of the report.
func RenderJSON(report Report) ([]byte, error) {
	payload := struct {
		AsOf        string              `json:"as_of"`
		Health      HealthSummary       `json:"health"`
		Queue       queueJSON           `json:"queue"`
		Scopes      map[string]int      `json:"scopes"`
		Generations map[string]int      `json:"generations"`
		Stages      []StageSummary      `json:"stages"`
		Domains     []domainBacklogJSON `json:"domains"`
	}{
		AsOf:        report.AsOf.UTC().Format(time.RFC3339),
		Health:      report.Health,
		Queue:       queueJSONFromReport(report.Queue),
		Scopes:      cloneCounts(report.ScopeTotals),
		Generations: cloneCounts(report.GenerationTotals),
		Stages:      slices.Clone(report.StageSummaries),
		Domains:     domainBacklogsJSON(report.DomainBacklogs),
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

func evaluateHealth(queue QueueSnapshot, generationTotals map[string]int, opts Options) HealthSummary {
	if queue.OverdueClaims > 0 {
		return HealthSummary{
			State: healthStalled,
			Reasons: []string{
				fmt.Sprintf("%d overdue claims suggest stuck workers", queue.OverdueClaims),
			},
		}
	}
	if queue.Outstanding > 0 && queue.InFlight == 0 && queue.OldestOutstandingAge >= opts.StallAfter {
		return HealthSummary{
			State: healthStalled,
			Reasons: []string{
				fmt.Sprintf(
					"backlog has %d outstanding items with no in-flight work for %s",
					queue.Outstanding,
					queue.OldestOutstandingAge,
				),
			},
		}
	}
	if queue.Failed > 0 || generationTotals["failed"] > 0 {
		reasons := make([]string, 0, 2)
		if queue.Failed > 0 {
			reasons = append(reasons, fmt.Sprintf("%d work items are terminally failed", queue.Failed))
		}
		if generationTotals["failed"] > 0 {
			reasons = append(reasons, fmt.Sprintf("%d generations are failed", generationTotals["failed"]))
		}
		return HealthSummary{
			State:   healthDegraded,
			Reasons: reasons,
		}
	}
	if queue.Outstanding > 0 || generationTotals["active"] > 0 || generationTotals["pending"] > 0 {
		reason := "work remains queued"
		if queue.InFlight > 0 {
			reason = fmt.Sprintf("%d work items are currently in flight", queue.InFlight)
		}
		return HealthSummary{
			State:   healthProgressing,
			Reasons: []string{reason},
		}
	}

	return HealthSummary{
		State:   healthHealthy,
		Reasons: []string{"no outstanding queue backlog"},
	}
}

func summarizeStages(rows []StageStatusCount) []StageSummary {
	byStage := make(map[string]*StageSummary, len(rows))
	for _, row := range rows {
		stageName := strings.TrimSpace(row.Stage)
		if stageName == "" {
			continue
		}
		stageSummary, ok := byStage[stageName]
		if !ok {
			stageSummary = &StageSummary{Stage: stageName}
			byStage[stageName] = stageSummary
		}
		switch strings.TrimSpace(row.Status) {
		case "pending":
			stageSummary.Pending += row.Count
		case "claimed":
			stageSummary.Claimed += row.Count
		case "running":
			stageSummary.Running += row.Count
		case "retrying":
			stageSummary.Retrying += row.Count
		case "succeeded":
			stageSummary.Succeeded += row.Count
		case "failed":
			stageSummary.Failed += row.Count
		}
	}

	stageNames := make([]string, 0, len(byStage))
	for stageName := range byStage {
		stageNames = append(stageNames, stageName)
	}
	sort.Strings(stageNames)

	summaries := make([]StageSummary, 0, len(stageNames))
	for _, stageName := range stageNames {
		summaries = append(summaries, *byStage[stageName])
	}

	return summaries
}

func topDomainBacklogs(rows []DomainBacklog, limit int) []DomainBacklog {
	filtered := make([]DomainBacklog, 0, len(rows))
	for _, row := range rows {
		if strings.TrimSpace(row.Domain) == "" {
			continue
		}
		filtered = append(filtered, row)
	}
	sort.Slice(filtered, func(i, j int) bool {
		if filtered[i].Outstanding != filtered[j].Outstanding {
			return filtered[i].Outstanding > filtered[j].Outstanding
		}
		if filtered[i].OldestAge != filtered[j].OldestAge {
			return filtered[i].OldestAge > filtered[j].OldestAge
		}
		return filtered[i].Domain < filtered[j].Domain
	})
	if len(filtered) > limit {
		filtered = filtered[:limit]
	}

	return filtered
}

func toCountMap(rows []NamedCount) map[string]int {
	counts := make(map[string]int, len(rows))
	for _, row := range rows {
		name := strings.TrimSpace(row.Name)
		if name == "" {
			continue
		}
		counts[name] += row.Count
	}

	return counts
}

func cloneCounts(values map[string]int) map[string]int {
	if len(values) == 0 {
		return map[string]int{}
	}
	cloned := make(map[string]int, len(values))
	for key, value := range values {
		cloned[key] = value
	}
	return cloned
}

func formatNamedTotals(values map[string]int) string {
	if len(values) == 0 {
		return "none"
	}

	keys := make([]string, 0, len(values))
	for key, value := range values {
		if value <= 0 {
			continue
		}
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i, j int) bool {
		return countOrder(keys[i]) < countOrder(keys[j]) ||
			(countOrder(keys[i]) == countOrder(keys[j]) && keys[i] < keys[j])
	})

	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, fmt.Sprintf("%s=%d", key, values[key]))
	}
	if len(parts) == 0 {
		return "none"
	}

	return strings.Join(parts, " ")
}

func countOrder(name string) int {
	switch name {
	case "active":
		return 0
	case "pending":
		return 1
	case "completed":
		return 2
	case "succeeded":
		return 3
	case "failed":
		return 4
	default:
		return 100
	}
}

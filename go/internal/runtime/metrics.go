package runtime

import (
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

const runtimeMetricsContentType = "text/plain; charset=utf-8"

// NewStatusMetricsHandler builds a shared Prometheus-style metrics surface from
// the same status reader used by the runtime admin report.
func NewStatusMetricsHandler(serviceName string, reader statuspkg.Reader) (http.Handler, error) {
	serviceName = strings.TrimSpace(serviceName)
	if serviceName == "" {
		return nil, fmt.Errorf("service name is required")
	}
	if reader == nil {
		return nil, fmt.Errorf("status reader is required")
	}

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		serveStatusMetrics(w, r, serviceName, reader)
	}), nil
}

func serveStatusMetrics(w http.ResponseWriter, r *http.Request, serviceName string, reader statuspkg.Reader) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		w.Header().Set("Allow", "GET, HEAD")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	report, err := statuspkg.LoadReport(r.Context(), reader, time.Now().UTC(), statuspkg.DefaultOptions())
	if err != nil {
		http.Error(w, fmt.Sprintf("load runtime metrics: %v", err), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", runtimeMetricsContentType)
	w.WriteHeader(http.StatusOK)
	if r.Method == http.MethodHead {
		return
	}

	_, _ = w.Write([]byte(renderStatusMetrics(serviceName, report)))
}

func renderStatusMetrics(serviceName string, report statuspkg.Report) string {
	builder := &strings.Builder{}
	quote := func(value string) string {
		return strconv.Quote(strings.TrimSpace(value))
	}

	writeGauge := func(name string, labels map[string]string, value string) {
		builder.WriteString(name)
		if len(labels) > 0 {
			builder.WriteString("{")
			keys := make([]string, 0, len(labels))
			for key := range labels {
				keys = append(keys, key)
			}
			sort.Strings(keys)
			for i, key := range keys {
				if i > 0 {
					builder.WriteString(",")
				}
				builder.WriteString(key)
				builder.WriteString("=")
				builder.WriteString(quote(labels[key]))
			}
			builder.WriteString("}")
		}
		builder.WriteString(" ")
		builder.WriteString(value)
		builder.WriteString("\n")
	}

	baseLabels := map[string]string{
		"service_name":      serviceName,
		"service_namespace": telemetry.DefaultServiceNamespace,
	}

	writeGauge("pcg_runtime_info", baseLabels, "1")
	writeGauge("pcg_runtime_scope_active", map[string]string{"service_name": serviceName}, strconv.Itoa(report.ScopeActivity.Active))
	writeGauge("pcg_runtime_scope_changed", map[string]string{"service_name": serviceName}, strconv.Itoa(report.ScopeActivity.Changed))
	writeGauge(
		"pcg_runtime_refresh_skipped_total",
		map[string]string{"service_name": serviceName},
		strconv.FormatUint(telemetry.SkippedRefreshCount(), 10),
	)
	for _, state := range []string{"healthy", "progressing", "degraded", "stalled"} {
		value := "0"
		if report.Health.State == state {
			value = "1"
		}
		writeGauge("pcg_runtime_health_state", map[string]string{
			"service_name": serviceName,
			"state":        state,
		}, value)
	}

	queue := report.Queue
	writeGauge("pcg_runtime_queue_total", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.Total))
	writeGauge("pcg_runtime_queue_outstanding", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.Outstanding))
	writeGauge("pcg_runtime_queue_pending", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.Pending))
	writeGauge("pcg_runtime_queue_in_flight", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.InFlight))
	writeGauge("pcg_runtime_queue_retrying", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.Retrying))
	writeGauge("pcg_runtime_queue_succeeded", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.Succeeded))
	writeGauge("pcg_runtime_queue_failed", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.Failed))
	writeGauge("pcg_runtime_queue_overdue_claims", map[string]string{"service_name": serviceName}, strconv.Itoa(queue.OverdueClaims))
	writeGauge(
		"pcg_runtime_queue_oldest_outstanding_age_seconds",
		map[string]string{"service_name": serviceName},
		fmt.Sprintf("%.0f", queue.OldestOutstandingAge.Seconds()),
	)

	for _, key := range sortedCountKeys(report.GenerationTotals) {
		writeGauge(
			"pcg_runtime_generation_total",
			map[string]string{
				"service_name": serviceName,
				"state":        key,
			},
			strconv.Itoa(report.GenerationTotals[key]),
		)
	}

	for _, row := range report.StageSummaries {
		labels := map[string]string{
			"service_name": serviceName,
			"stage":        row.Stage,
		}
		writeGauge("pcg_runtime_stage_items", mergeLabels(labels, "status", "pending"), strconv.Itoa(row.Pending))
		writeGauge("pcg_runtime_stage_items", mergeLabels(labels, "status", "claimed"), strconv.Itoa(row.Claimed))
		writeGauge("pcg_runtime_stage_items", mergeLabels(labels, "status", "running"), strconv.Itoa(row.Running))
		writeGauge("pcg_runtime_stage_items", mergeLabels(labels, "status", "retrying"), strconv.Itoa(row.Retrying))
		writeGauge("pcg_runtime_stage_items", mergeLabels(labels, "status", "succeeded"), strconv.Itoa(row.Succeeded))
		writeGauge("pcg_runtime_stage_items", mergeLabels(labels, "status", "failed"), strconv.Itoa(row.Failed))
	}

	for _, row := range report.DomainBacklogs {
		labels := map[string]string{
			"service_name": serviceName,
			"domain":       row.Domain,
		}
		writeGauge("pcg_runtime_domain_outstanding", labels, strconv.Itoa(row.Outstanding))
		writeGauge("pcg_runtime_domain_retrying", labels, strconv.Itoa(row.Retrying))
		writeGauge("pcg_runtime_domain_failed", labels, strconv.Itoa(row.Failed))
		writeGauge(
			"pcg_runtime_domain_oldest_age_seconds",
			labels,
			fmt.Sprintf("%.0f", row.OldestAge.Seconds()),
		)
	}

	return builder.String()
}

func mergeLabels(labels map[string]string, key, value string) map[string]string {
	merged := make(map[string]string, len(labels)+1)
	for labelKey, labelValue := range labels {
		merged[labelKey] = labelValue
	}
	merged[key] = value
	return merged
}

func sortedCountKeys(values map[string]int) []string {
	keys := make([]string, 0, len(values))
	for key, value := range values {
		if strings.TrimSpace(key) == "" || value == 0 {
			continue
		}
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

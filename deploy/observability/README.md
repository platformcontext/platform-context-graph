# PlatformContextGraph Observability Configuration

This directory contains Prometheus alerting rules and OTEL collector configuration for PCG.

## Files

- `otel-collector-config.yaml` - OpenTelemetry Collector configuration for metrics and traces
- `alerts.yaml` - Standalone Prometheus alert rules (for direct Prometheus deployment)
- `prometheus-rule.yaml` - Kubernetes PrometheusRule CR (for kube-prometheus-stack)

## Alert Groups

### pcg.pipeline (5 alerts)
Pipeline health monitoring for fact emission, projection, and reduction.

| Alert | Severity | Threshold | Purpose |
|-------|----------|-----------|---------|
| PCGFactQueueStale | critical | >1 hour | Oldest work item aging detection |
| PCGProjectionErrorRateHigh | warning | >5% failure rate | Projection stage failures |
| PCGReducerErrorRateHigh | warning | >5% failure rate | Reducer intent execution failures |
| PCGSharedProjectionBacklog | warning | >500 pending | Shared projection capacity monitoring |
| PCGCollectorStalled | critical | 15min no facts | Git collector stall detection |

### pcg.api (3 alerts)
HTTP API and MCP request monitoring.

| Alert | Severity | Threshold | Purpose |
|-------|----------|-----------|---------|
| PCGAPIErrorRateHigh | warning | >1% 5xx rate | HTTP request failures |
| PCGAPIP99LatencyHigh | warning | >5s P99 | API performance degradation |
| PCGMCPToolErrorRateHigh | warning | >2% failure rate | MCP tool invocation failures |

### pcg.database (3 alerts)
Neo4j and Postgres performance monitoring.

| Alert | Severity | Threshold | Purpose |
|-------|----------|-----------|---------|
| PCGPostgresLatencyHigh | warning | >1s P99 | Postgres query performance |
| PCGNeo4jLatencyHigh | warning | >2s P99 | Neo4j query performance |
| PCGNeo4jQueryErrors | critical | >0.1 errors/sec | Neo4j connectivity or query failures |

### pcg.throughput (3 alerts)
Pipeline throughput and backlog monitoring.

| Alert | Severity | Threshold | Purpose |
|-------|----------|-----------|---------|
| PCGFactEmissionRateDropped | warning | >50% drop | Collector throughput degradation |
| PCGProjectionThroughputMismatch | warning | 2x rate mismatch | Projection backlog growth |
| PCGReducerIntentBacklog | warning | 1.5x rate mismatch | Reducer intent queue growth |

## Deployment

### Standalone Prometheus

Load alert rules directly:

```bash
# Add to prometheus.yml
rule_files:
  - /etc/prometheus/rules/pcg-alerts.yaml

# Copy alerts to Prometheus container
kubectl create configmap pcg-alerts --from-file=alerts.yaml
kubectl patch deployment prometheus -p '{"spec":{"template":{"spec":{"volumes":[{"name":"pcg-alerts","configMap":{"name":"pcg-alerts"}}]}}}}'
```

### kube-prometheus-stack

Deploy as PrometheusRule CR:

```bash
kubectl apply -f prometheus-rule.yaml
```

The PrometheusRule will be automatically discovered by the Prometheus Operator and loaded.

## Verification

Check that alerts are loaded:

```bash
# Via kubectl
kubectl get prometheusrules pcg-alerts -o yaml

# Via Prometheus UI
# Navigate to Status -> Rules
# Filter for "pcg."
```

Test alert evaluation:

```bash
# Force an alert to fire (example: stop ingester)
kubectl scale statefulset pcg-ingester --replicas=0

# Wait 15 minutes, then check Prometheus UI -> Alerts
# PCGCollectorStalled should fire

# Restore
kubectl scale statefulset pcg-ingester --replicas=1
```

## Runbook References

Every alert includes a detailed runbook with:

1. Initial diagnostic commands (kubectl, logs, metrics)
2. Jaeger trace filtering guidance (service, phase, attributes)
3. Common failure patterns and their causes
4. Specific metrics to check for root cause analysis
5. Remediation steps and tuning guidance
6. Escalation criteria

Example runbook workflow for `PCGProjectionErrorRateHigh`:

```bash
# 1. Check failure rate by status
curl -s 'http://prometheus:9090/api/v1/query?query=rate(pcg_dp_projections_completed_total[5m])' | jq

# 2. Open Jaeger UI
# Filter: service_name=pcg-ingester, pipeline_phase=projection
# Look for error spans with failure_class tag

# 3. Check stage-specific failures
curl -s 'http://prometheus:9090/api/v1/query?query=pcg_dp_projector_stage_duration_seconds' | jq

# 4. Review logs with structured filtering
kubectl logs -l app=pcg-ingester | grep 'failure_class'

# 5. Check backing service health
curl -s 'http://prometheus:9090/api/v1/query?query=rate(pcg_dp_neo4j_query_errors_total[5m])' | jq
```

## Metric Sources

All metrics referenced in alerts are emitted by:

- **Go services**: `go/internal/telemetry/instruments.go` (pcg_dp_* prefix)
- **Shared runtime status metrics**: `go/internal/status/*` and mounted
  `/metrics` handlers (pcg_runtime_* families retained for operator continuity)
- **Instrumented storage**: `go/internal/storage/{neo4j,postgres}/instrumented.go`

See `docs/docs/reference/telemetry/index.md` for complete metric catalog.

## Integration with Grafana Dashboards

These alerts complement the existing dashboards:

- `docs/dashboards/pipeline-slo.json` - Overall pipeline success rate and error budget
- `docs/dashboards/ingester.json` - Ingester-specific metrics and queue depth
- `docs/dashboards/reducer.json` - Reducer execution and shared projection metrics
- `docs/dashboards/database-performance.json` - Neo4j and Postgres query latency
- `docs/dashboards/overview.json` - High-level service health overview

Alert annotations include references to specific dashboard panels for context.

## Alertmanager Configuration

Example Alertmanager routing for PCG alerts:

```yaml
route:
  receiver: 'default'
  group_by: ['alertname', 'service', 'component']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty-critical'
      continue: true
    - match:
        severity: warning
      receiver: 'slack-warnings'

receivers:
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: '<your-pagerduty-key>'
  - name: 'slack-warnings'
    slack_configs:
      - api_url: '<your-slack-webhook>'
        channel: '#pcg-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'
```

## Tuning Alert Thresholds

Thresholds are based on observed behavior in the SLO dashboard and telemetry docs. Adjust based on your deployment:

| Alert | Current Threshold | Tuning Guidance |
|-------|-------------------|-----------------|
| PCGFactQueueStale | 1 hour | Increase for slower repos, decrease for strict SLOs |
| Projection/ReducerErrorRate | 5% | Lower to 2-3% for production, higher for dev |
| SharedProjectionBacklog | 500 intents | Scale with partition count (100 per partition) |
| APIErrorRate | 1% | Lower to 0.5% for strict availability SLOs |
| APIP99Latency | 5s | Lower to 2-3s for interactive use cases |
| PostgresP99 | 1s | Lower to 500ms for high-throughput scenarios |
| Neo4jP99 | 2s | Lower to 1s if query optimization is complete |

Edit thresholds in `alerts.yaml` or `prometheus-rule.yaml` and reapply.

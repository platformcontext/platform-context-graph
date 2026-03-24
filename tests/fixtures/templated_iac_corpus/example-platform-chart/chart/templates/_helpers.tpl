{{- define "pcg.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pcg.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "pcg.labels" -}}
helm.sh/chart: {{ include "pcg.name" . }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "pcg.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "pcg.selectorLabels" -}}
app.kubernetes.io/name: {{ include "pcg.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "pcg.apiFullname" -}}
{{- printf "%s-api" (include "pcg.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pcg.ingesterHeadlessServiceName" -}}
{{- printf "%s-ingester" (include "pcg.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pcg.apiSelectorLabels" -}}
{{- include "pcg.selectorLabels" . }}
app.kubernetes.io/component: api
{{- end -}}

{{- define "pcg.ingesterSelectorLabels" -}}
{{- include "pcg.selectorLabels" . }}
app.kubernetes.io/component: ingester
{{- end -}}

{{- define "pcg.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "pcg.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "pcg.dataClaimName" -}}
{{- if .Values.ingester.persistence.existingClaim -}}
{{- .Values.ingester.persistence.existingClaim -}}
{{- else -}}
{{- printf "%s-data" (include "pcg.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "pcg.renderEnvMap" -}}
{{- range $key, $value := . }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- end -}}

{{- define "pcg.renderEnvMaps" -}}
{{- range $envMap := . }}
{{- if $envMap }}
{{- include "pcg.renderEnvMap" $envMap }}
{{- end }}
{{- end }}
{{- end -}}

{{- define "pcg.joinStringMap" -}}
{{- $map := . -}}
{{- $items := list -}}
{{- range $key := keys $map | sortAlpha -}}
{{- $items = append $items (printf "%s=%v" $key (index $map $key)) -}}
{{- end -}}
{{- join "," $items -}}
{{- end -}}

{{- define "pcg.renderOtelEnv" -}}
{{- if .Values.observability.otel.enabled }}
- name: PCG_DEPLOYMENT_ENVIRONMENT
  value: {{ .Values.observability.environment | quote }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ .Values.observability.otel.endpoint | quote }}
- name: OTEL_EXPORTER_OTLP_PROTOCOL
  value: {{ .Values.observability.otel.protocol | quote }}
- name: OTEL_EXPORTER_OTLP_INSECURE
  value: {{ ternary "true" "false" .Values.observability.otel.insecure | quote }}
- name: OTEL_EXPORTER_OTLP_HEADERS
  value: {{ include "pcg.joinStringMap" .Values.observability.otel.headers | quote }}
- name: OTEL_TRACES_EXPORTER
  value: "otlp"
- name: OTEL_METRICS_EXPORTER
  value: "otlp"
- name: OTEL_LOGS_EXPORTER
  value: "none"
- name: OTEL_METRIC_EXPORT_INTERVAL
  value: {{ mul (int .Values.observability.otel.metricExportIntervalSeconds) 1000 | quote }}
- name: OTEL_PYTHON_FASTAPI_EXCLUDED_URLS
  value: {{ join "," .Values.observability.otel.excludedUrls | quote }}
- name: OTEL_RESOURCE_ATTRIBUTES
  value: {{ include "pcg.joinStringMap" .Values.observability.otel.resourceAttributes | quote }}
{{- end }}
{{- end -}}

{{- define "pcg.renderContentStoreEnv" -}}
{{- if and .Values.contentStore.secretName .Values.contentStore.dsnKey }}
- name: PCG_CONTENT_STORE_DSN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.contentStore.secretName }}
      key: {{ .Values.contentStore.dsnKey }}
- name: PCG_POSTGRES_DSN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.contentStore.secretName }}
      key: {{ .Values.contentStore.dsnKey }}
{{- else if .Values.contentStore.dsn }}
- name: PCG_CONTENT_STORE_DSN
  value: {{ .Values.contentStore.dsn | quote }}
- name: PCG_POSTGRES_DSN
  value: {{ .Values.contentStore.dsn | quote }}
{{- end }}
{{- end -}}

{{- define "pcg.argocdAnnotations" -}}
argocd.argoproj.io/sync-wave: {{ default "1" .Values.argocd.syncWave | quote }}
{{- end -}}

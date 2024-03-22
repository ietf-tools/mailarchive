{{/*
Expand the name of the chart.
*/}}
{{- define "mailarchive.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "mailarchive.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "mailarchive.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "mailarchive.labels" -}}
helm.sh/chart: {{ include "mailarchive.chart" . }}
{{ include "mailarchive.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "mailarchive.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mailarchive.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "mailarchive.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "mailarchive.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "mailarchive.db.env" -}}
- name: DATABASES_HOST
  value: mailarchive-postgresql
- name: DATABASES_NAME
  value: {{ .Values.postgresql.postgresqlDatabase }}
- name: DATABASES_USER
  value: {{ .Values.postgresql.postgresqlUsername }}
- name: DATABASES_PASSWORD
  value: {{ .Values.postgresql.postgresqlPassword }}
{{- end }}
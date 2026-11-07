{{/* Names */}}
{{- define "clearhire.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "clearhire.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else if contains (include "clearhire.name" .) .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "clearhire.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "clearhire.secretName" -}}
{{- .Values.secrets.existingSecret | default (printf "%s-secrets" (include "clearhire.fullname" .)) -}}
{{- end -}}

{{/* Labels: (dict "ctx" $ "component" "api") */}}
{{- define "clearhire.selectorLabels" -}}
app.kubernetes.io/name: {{ include "clearhire.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "clearhire.labels" -}}
{{ include "clearhire.selectorLabels" . }}
app.kubernetes.io/part-of: clearhire
app.kubernetes.io/version: {{ .ctx.Values.image.tag | default .ctx.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .ctx.Chart.Name .ctx.Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Which in-cluster services a pod may reach. The NetworkPolicies admit exactly the pods carrying these
labels: (list "postgres" "redis")
*/}}
{{- define "clearhire.accessLabels" -}}
{{- range . }}
clearhire.io/{{ . }}-client: "true"
{{- end }}
{{- end -}}

{{/* A Clearhire image: (dict "ctx" $ "name" "api") */}}
{{- define "clearhire.image" -}}
{{- $tag := .ctx.Values.image.tag | default .ctx.Chart.AppVersion -}}
{{- if .ctx.Values.image.registry -}}
{{- printf "%s/clearhire-%s:%s" (trimSuffix "/" .ctx.Values.image.registry) .name $tag -}}
{{- else -}}
{{- printf "clearhire-%s:%s" .name $tag -}}
{{- end -}}
{{- end -}}

{{- define "clearhire.url" -}}
{{- printf "%s://%s" .scheme .host -}}
{{- end -}}

{{- define "clearhire.careersUrl" -}}
{{- include "clearhire.url" (dict "scheme" .Values.hosts.scheme "host" .Values.hosts.careers) -}}
{{- end -}}

{{- define "clearhire.consoleUrl" -}}
{{- include "clearhire.url" (dict "scheme" .Values.hosts.scheme "host" .Values.hosts.console) -}}
{{- end -}}

{{- define "clearhire.llmUrl" -}}
{{- if .Values.llm.enabled -}}
{{- printf "http://%s-llm:11434/v1" (include "clearhire.fullname" .) -}}
{{- else -}}
{{- .Values.llm.url -}}
{{- end -}}
{{- end -}}

{{- define "clearhire.chainUrl" -}}
{{- if .Values.chain.enabled -}}
{{- printf "http://%s-chain:8545" (include "clearhire.fullname" .) -}}
{{- else -}}
{{- .Values.anchoring.rpcUrl -}}
{{- end -}}
{{- end -}}

{{/* Locked-down containers: no root, no privilege escalation, no capabilities, read-only root. */}}
{{- define "clearhire.containerSecurity" -}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
{{- end -}}

{{/* (dict "ctx" $ "uid" 10001) */}}
{{- define "clearhire.podSecurity" -}}
securityContext:
  {{- toYaml .ctx.Values.podSecurityContext | nindent 2 }}
  {{- with .uid }}
  runAsUser: {{ . }}
  runAsGroup: {{ . }}
  fsGroup: {{ . }}
  {{- end }}
{{- end -}}

{{- define "clearhire.podDefaults" -}}
automountServiceAccountToken: false
enableServiceLinks: false
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/* The backend's environment: the shared ConfigMap plus the secrets each process needs. */}}
{{- define "clearhire.backendEnv" -}}
envFrom:
  - configMapRef:
      name: {{ include "clearhire.fullname" . }}-config
env:
  - name: CLEARHIRE_DATABASE_URL
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: database-url } }
  - name: CLEARHIRE_REDIS_URL
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: redis-url } }
  - name: CLEARHIRE_JWT_SECRET
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: jwt-secret } }
  - name: CLEARHIRE_BOT_SECRET
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: bot-secret } }
  - name: CLEARHIRE_LLM_API_KEY
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: llm-api-key, optional: true } }
{{- end -}}

{{/* Waits for the database, and with "migrated" for the schema this code needs. */}}
{{- define "clearhire.waitForDatabase" -}}
- name: wait-for-database
  image: {{ include "clearhire.image" (dict "ctx" .ctx "name" "api") }}
  imagePullPolicy: {{ .ctx.Values.image.pullPolicy }}
  command: ["clearhire", "wait-db", "--timeout", "900"{{ if .migrated }}, "--migrated"{{ end }}]
  env:
    - name: CLEARHIRE_DATABASE_URL
      valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" .ctx }}, key: database-url } }
    - name: CLEARHIRE_EMBEDDING_MODEL
      value: hash
  {{- include "clearhire.containerSecurity" . | nindent 2 }}
  resources:
    requests: { cpu: 10m, memory: 64Mi }
    limits: { memory: 256Mi }
{{- end -}}

{{/* Scheduling for the pods that share the files volume. */}}
{{- define "clearhire.filesAffinity" -}}
{{- if eq .Values.files.accessMode "ReadWriteOnce" }}
affinity:
  podAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - topologyKey: kubernetes.io/hostname
        labelSelector:
          matchLabels:
            app.kubernetes.io/instance: {{ .Release.Name }}
            clearhire.io/files: "true"
{{- end }}
{{- end -}}

{{- define "clearhire.filesVolume" -}}
- name: files
  persistentVolumeClaim:
    claimName: {{ include "clearhire.fullname" . }}-files
- name: tmp
  emptyDir: { sizeLimit: 1Gi }
{{- end -}}

{{- define "clearhire.filesMounts" -}}
- name: files
  mountPath: /data/files
- name: tmp
  mountPath: /tmp
{{- end -}}

{{- define "clearhire.checksums" -}}
checksum/config: {{ include (print .Template.BasePath "/config.yaml") . | sha256sum }}
checksum/secret: {{ include "clearhire.secretInputs" . }}
{{- end -}}

{{- /*
What the Secret is made from, hashed: the values a person sets, not the rendered Secret. Each include of
secret.yaml renders it again, and on install every render draws new random passwords, so a hash of the
output never matches the Secret actually stored; the first upgrade then changed every checksum and
restarted every pod, the database included. Generated values never change after install (they are read
back), so they need no place in the hash.
*/}}
{{- define "clearhire.secretInputs" -}}
{{- dict "secrets" .Values.secrets "postgres" (pick .Values.postgres "password" "externalUrl") "redis" (pick .Values.redis "password" "externalUrl") | toJson | sha256sum }}
{{- end -}}

{{- define "clearhire.llmEnv" -}}
env:
  - name: HOME
    value: /tmp
  - name: OLLAMA_MODELS
    value: /models
  - name: OLLAMA_KEEP_ALIVE
    value: 24h
  - name: OLLAMA_CONTEXT_LENGTH
    value: "16384"
  - name: OLLAMA_NUM_PARALLEL
    value: "2"
{{- end -}}

{{- define "clearhire.llmMounts" -}}
volumeMounts:
  - name: models
    mountPath: /models
  - name: tmp
    mountPath: /tmp
{{- end -}}

{{/* The anchor service's environment: the database, the chain and the publisher's key, nothing else. */}}
{{- define "clearhire.anchorEnv" -}}
env:
  - name: CLEARHIRE_DATABASE_URL
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: database-url } }
  - name: CLEARHIRE_JWT_SECRET
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: jwt-secret } }
  - name: CLEARHIRE_ANCHOR_PRIVATE_KEY
    valueFrom: { secretKeyRef: { name: {{ include "clearhire.secretName" . }}, key: anchor-private-key } }
  - name: CLEARHIRE_CHAIN_RPC_URL
    value: {{ include "clearhire.chainUrl" . | quote }}
  - name: CLEARHIRE_ANCHOR_CONTRACT
    value: {{ .Values.anchoring.contract | quote }}
  - name: CLEARHIRE_ANCHOR_PERIOD_SECONDS
    value: {{ .Values.anchoring.periodSeconds | quote }}
  - name: CLEARHIRE_EMBEDDING_MODEL
    value: hash  # anchoring reads no CVs: skip loading the model
{{- end -}}

{{/* The Gateway's (or the Ingress controller's) proxy pods, as a NetworkPolicy peer. */}}
{{- define "clearhire.gatewayPeer" -}}
namespaceSelector:
  matchLabels:
    kubernetes.io/metadata.name: {{ .Values.networkPolicy.gatewayNamespace | default .Release.Namespace }}
{{- with .Values.networkPolicy.gatewayPodLabels }}
podSelector:
  matchLabels:
    {{- toYaml . | nindent 4 }}
{{- end }}
{{- end -}}

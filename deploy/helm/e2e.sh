#!/usr/bin/env bash
# End to end on a throwaway kind cluster: install Envoy Gateway and the chart, then check what a user and an
# operator would see. CI runs this (.github/workflows/k8s.yml); locally, from the repository root:
#   docker build -f backend/Dockerfile -t clearhire-api:ci . && docker build -f portal/Dockerfile -t clearhire-portal:ci . \
#     && docker build -f console/Dockerfile -t clearhire-console:ci .
#   bash deploy/helm/e2e.sh            (KEEP=1 leaves the cluster running afterwards)
# Needs docker, kind, kubectl, helm, curl and jq.
set -euo pipefail

CLUSTER=${CLUSTER:-clearhire-e2e}
NS=clearhire
ENVOY_GATEWAY=v1.9.2
here=$(cd "$(dirname "$0")" && pwd)
k() { kubectl --context "kind-$CLUSTER" "$@"; }
h() { helm --kube-context "kind-$CLUSTER" "$@"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFAIL: %s\033[0m\n' "$*"; exit 1; }
pass() { printf '\033[32mok\033[0m  %s\n' "$*"; }

forward_pid=""
cleanup() {
  status=$?
  [ -n "$forward_pid" ] && kill "$forward_pid" 2>/dev/null || true
  if [ $status -ne 0 ]; then
    echo "--- pods"; k -n $NS get pods -o wide || true
    echo "--- events"; k -n $NS get events --sort-by=.lastTimestamp | tail -30 || true
    for pod in $(k -n $NS get pods -o name 2>/dev/null); do
      echo "--- $pod"; k -n $NS logs "$pod" --all-containers --tail=40 || true
    done
  fi
  if [ -z "${KEEP:-}" ]; then kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

step "cluster"
kind get clusters 2>/dev/null | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER" --config "$here/kind.yaml" --wait 120s
for image in clearhire-api:ci clearhire-portal:ci clearhire-console:ci; do
  kind load docker-image --name "$CLUSTER" "$image"
done

step "Envoy Gateway $ENVOY_GATEWAY (it brings the Gateway API CRDs)"
h upgrade --install eg oci://docker.io/envoyproxy/gateway-helm --version "$ENVOY_GATEWAY" \
  -n envoy-gateway-system --create-namespace --wait --timeout 5m
k apply -f "$here/gateway.yaml"
k wait --for=condition=Accepted gatewayclass/eg --timeout=120s

step "install Clearhire (migrations, then the API; the demo data loads after install)"
started=$(date +%s)
h upgrade --install clearhire "$here/clearhire" -n $NS --create-namespace \
  -f "$here/clearhire/ci/kind-values.yaml" --wait --wait-for-jobs --timeout 30m
echo "installed and seeded in $(( $(date +%s) - started ))s"
k -n $NS get pods

step "through the Gateway"
k -n $NS wait --for=condition=Programmed gateway/clearhire --timeout=180s || true
service=$(k -n envoy-gateway-system get svc -l gateway.envoyproxy.io/owning-gateway-name=clearhire -o name | head -1)
[ -n "$service" ] || fail "no Envoy service for the Gateway"
k -n envoy-gateway-system port-forward "$service" 18080:80 >/dev/null 2>&1 &
forward_pid=$!
for _ in $(seq 30); do curl -s -o /dev/null http://127.0.0.1:18080 && break; sleep 1; done

careers() { curl -s -H "Host: careers.clearhire.test" "$@"; }
console() { curl -s -H "Host: console.clearhire.test" "$@"; }
code() { curl -s -o /dev/null -w '%{http_code}' -H "Host: $1" "http://127.0.0.1:18080$2"; }

vacancies=$(careers http://127.0.0.1:18080/api/public/vacancies | jq 'if type == "array" then length else (.items | length) end')
[ "$vacancies" -gt 0 ] || fail "the careers API lists no vacancies"
pass "careers: /api/public/vacancies lists $vacancies open roles from the seeded demo"
careers http://127.0.0.1:18080/ | grep -q "<html" || fail "careers home page"
pass "careers: the Next.js home page renders"
[ "$(code careers.clearhire.test /api/health)" = 404 ] || fail "careers must not expose /api/health"
[ "$(code careers.clearhire.test /metrics)" = 404 ] || fail "careers must not expose /metrics"
pass "careers: the staff API and /metrics are not reachable on the public site (404)"
console -D - -o /dev/null http://127.0.0.1:18080/ | grep -qi "content-security-policy: default-src 'self'" || fail "console CSP"
pass "console: the Angular app is served with its Content-Security-Policy"
token=$(console -X POST http://127.0.0.1:18080/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"recruiter@clearhire.demo","password":"clearhire-demo"}' | jq -r .access_token)
[ -n "$token" ] && [ "$token" != null ] || fail "recruiter login"
auth=(-H "Authorization: Bearer $token")
candidates=$(console "${auth[@]}" "http://127.0.0.1:18080/api/candidates?limit=1" | jq '.total // length')
pass "console: a recruiter signs in; the API holds $candidates candidates"
console "${auth[@]}" http://127.0.0.1:18080/api/audit/verify | jq -e .valid >/dev/null || fail "audit log hash chain"
pass "console: the audit log's hash chain verifies"

step "anchoring on the in-cluster chain"
deployed=$(k -n $NS logs job/clearhire-deploy-contract | tail -1)
[ "$deployed" = "0x5FbDB2315678afecb367f032d93F642f64180aa3" ] || fail "contract deployed at $deployed"
pass "the post-install job deployed AuditAnchor at $deployed"
k -n $NS exec deploy/clearhire-anchor -- clearhire anchor --now
check=$(console "${auth[@]}" http://127.0.0.1:18080/api/audit/anchors/check)
echo "$check" | jq -e '.reachable and .anchors >= 1 and .matching == .anchors' >/dev/null || fail "anchors: $check"
proof=$(console "${auth[@]}" http://127.0.0.1:18080/api/audit/1/proof)
echo "$proof" | jq -e .verified_on_chain >/dev/null || fail "proof: $proof"
pass "the audit log is anchored, matches the chain, and entry 1 is proven by the contract"

step "helm test: services answer in-cluster, NetworkPolicies refuse non-clients"
h test clearhire -n $NS --logs --timeout 3m

step "a rolling upgrade under load drops no requests"
total=0 failed=0
(
  while :; do
    c=$(code careers.clearhire.test /api/public/vacancies)
    echo "$c"
    sleep 0.2
  done
) > /tmp/clearhire-e2e-codes &
load_pid=$!
h upgrade clearhire "$here/clearhire" -n $NS --reuse-values --set config.retentionDays=400 \
  --wait --wait-for-jobs --timeout 15m
sleep 3
kill $load_pid
total=$(wc -l < /tmp/clearhire-e2e-codes)
failed=$(grep -cv '^200$' /tmp/clearhire-e2e-codes || true)
k -n $NS get jobs
[ "$(k -n $NS get job clearhire-migrate-2 -o jsonpath='{.status.succeeded}')" = 1 ] || fail "revision 2's migration job"
[ "$failed" = 0 ] || fail "$failed of $total requests failed during the upgrade: $(sort /tmp/clearhire-e2e-codes | uniq -c | tr '\n' ' ')"
pass "the API and worker rolled to a new config (migration job 2 ran first); $total requests during it, none failed"

printf '\n\033[32mall end-to-end checks passed\033[0m\n'

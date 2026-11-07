# Clearhire on Kubernetes

A Helm chart for the whole platform, tested end to end on a throwaway kind cluster in CI. The single-host
Docker Compose deployment (`deploy/compose.yaml`) is what runs the live demo; this is the same system
for a cluster.

```
            Gateway (Gateway API; Envoy Gateway in CI)
              │ careers host                 │ console host
              ├─ /api/public/* ─┐            ├─ /api/* ─┐
              └─ /* ─► portal ──┤            └─ /* ─► console (nginx, static Angular)
                                ▼                       ▼
                     api (2+ replicas, HPA, PDB) ◄──────┘
                       │  waits for: migrate job (one per release revision)
    worker ──► redis ◄─┤  bot (1 replica, long-polls Telegram)
       │               ├─► postgres + pgvector
       └───────────────┼─► llm (Ollama on a GPU node, optional)
                       └─► chain (Anvil, optional) ◄── anchor (the only pod with the signing key)
```

## Install

```bash
helm install clearhire oci://ghcr.io/kyan9400/charts/clearhire --version 0.1.0 \
  -n clearhire --create-namespace \
  --set hosts.careers=careers.example.com --set hosts.console=console.example.com \
  --set gateway.enabled=true --set gateway.create=true --set gateway.className=<your GatewayClass> \
  --set gateway.listeners.httpsSecretName=clearhire-tls
```

Or attach the routes to a Gateway the cluster already has (`gateway.parentRefs`), or use a plain Ingress
(`ingress.enabled`). `ci/full-values.yaml` switches everything on (bot, GPU LLM, anchoring on a public
testnet, ServiceMonitor) and `ci/external-values.yaml` uses a managed database and cache with secrets
from outside the chart. Every value is checked by `values.schema.json`: a short JWT secret, a malformed
contract address or an unknown key fails at `helm install`, not at runtime.

## How it is put together

- **Migrations before traffic.** Each release revision runs its own `migrate-<revision>` Job. The API,
  the worker and the anchor service start with an init container, `clearhire wait-db --migrated`, that
  waits until the database holds every migration the code needs. Readiness is `/api/ready` (the database
  answers and the schema is current), liveness is `/api/health`, and a startup probe covers loading the
  embedding model. A database already at a newer release's revision counts as current, so a rollback
  still starts (migrations are written add-first, remove-a-release-later).
- **Secrets generated once, kept forever.** Left empty, the database, Redis, JWT and bot secrets are
  generated on the first install and read back with `lookup` on every upgrade, so an upgrade never
  rotates a password under a running database. Or bring your own Secret (`secrets.existingSecret`).
- **Least privilege.** Every container runs as a non-root user with a read-only root filesystem, no
  capabilities, no privilege escalation and the runtime's seccomp profile; no pod mounts a service-account
  token. Only the anchor pod (and the one-off contract deployment) reads the chain key.
- **NetworkPolicies.** Everything is denied by default. The front ends accept only the Gateway's proxies;
  the API accepts the Gateway and pods labelled as its clients (portal, bot); PostgreSQL, Redis, the LLM
  and the chain accept only their labelled clients. So `X-Forwarded-For`, which the API trusts for its
  rate limits, can only come from the Gateway.
- **Availability.** The API and the portal run two or more replicas with HPAs, PodDisruptionBudgets,
  `maxUnavailable: 0` rolling updates and a preStop pause so the Gateway drops a pod before it stops.
  The bot and the anchor service are deliberately single (`Recreate`): two Telegram long-pollers are
  refused, and two publishers would race for the same period.
- **Shared files.** Uploaded CVs live on one volume shared by the API and the worker. With a
  ReadWriteOnce class they are scheduled onto the same node (pod affinity); with ReadWriteMany they
  spread out.

## The end-to-end test

`bash deploy/helm/e2e.sh` (CI: `.github/workflows/k8s.yml`) builds a kind cluster with NetworkPolicy
enforcement, installs Envoy Gateway and the chart with the demo data and a local chain, then checks:

1. through the Gateway: the careers site and its public API work; `/api/health` and `/metrics` are not
   reachable on the public host; the console is served with its Content-Security-Policy; a recruiter
   signs in; the audit log's hash chain verifies;
2. anchoring: the post-install Job deployed the contract, the anchor service anchors the log, the log
   matches the chain and the contract proves an entry;
3. `helm test`: every service answers in-cluster, and a pod without the client labels is refused by
   PostgreSQL, Redis and the API;
4. a rolling upgrade under load: a config change rolls the API and the worker (after revision 2's
   migration job) while requests run against the careers API, and none fails.

Before that, the `chart` job lints the chart with every value set, validates the rendered manifests
against Kubernetes 1.34 to 1.36 and the Gateway API and prometheus-operator schemas with kubeconform,
and checks that the schema refuses bad values.

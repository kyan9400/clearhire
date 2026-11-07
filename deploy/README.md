# Deploying Clearhire on one Docker host

The live demo runs this way on a shared GPU server: careers site and recruiter console behind Caddy with
automatic HTTPS, the API and a background worker, PostgreSQL with pgvector, Redis, and a local LLM.

```
                 :443 ─► caddy ─┬─► portal (Next.js)           careers host
                                ├─► api (FastAPI) ◄──┐          /api/public/* only on the careers host
                                └─► console (static) │          console host: everything under /api
       worker (Taskiq) ─ redis ─────────────────────┤
                       postgres + pgvector ◄────────┤
                       llm (Ollama, GPU) ◄──────────┘          never reachable from outside
```

## First start

```bash
cp deploy/.env.example deploy/.env      # host names, generated secrets
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --build
docker compose -f deploy/compose.yaml --env-file deploy/.env exec llm ollama pull qwen3.5:9b
docker compose -f deploy/compose.yaml --env-file deploy/.env run --rm --no-deps worker \
  clearhire seed --dataset datasets/synthetic --password <demo password>
```

Without a domain, `<ip-with-dashes>.sslip.io` resolves to the server and Caddy gets real certificates for it.

## Things this host taught us

- **GPU through Vulkan.** Ollama's CUDA build needs NVIDIA driver 550+; the host has 535 and upgrading it
  means rebooting a shared server. `deploy/llm/Dockerfile` runs Ollama on the same GPU through Vulkan
  instead: the NVIDIA Vulkan driver loaded through EGL (headless servers have no GLX), plus two X11
  libraries the Ollama image lacks. Qwen 3.5 9B runs 100% on the GPU at about 38 tokens/s.
- **autoheal restarts any unhealthy container.** The host runs `willfarrell/autoheal` with
  `AUTOHEAL_CONTAINER_LABEL=all`. One-off commands inherited the API image's HTTP health check, turned
  unhealthy after a minute and were restarted mid-run. The health check now lives on the `api` service
  only; run one-off commands from `worker`, which has none.
- **Watchtower must not touch us.** Every service carries `com.centurylinklabs.watchtower.enable=false`,
  so a database is never upgraded underneath the data.
- **Build cache fills the disk.** The API image carries PyTorch; a few rebuilds left 20 GB of cache and
  filled a 97 GB disk. After deploying: `docker builder prune -af`.
- **Only Caddy publishes ports.** The API, the database and the model are on an internal network; the
  careers host exposes only `/api/public/*`, and `/metrics` answers 404 from outside.

## Tests on the server

`sh backend/scripts/test-in-docker.sh` runs the whole backend suite (C++ matcher, OCR, PostgreSQL) in
throwaway containers on a private network, and removes them afterwards.

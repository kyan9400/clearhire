#!/usr/bin/env sh
# The bot's tests against a throwaway Redis, as CI runs them.   sh backend/scripts/test-bot-in-docker.sh
set -eu
run="clearhire-bottest-$$"
cleanup() { docker rm -f "$run-redis" >/dev/null 2>&1 || true; docker network rm "$run" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker network create "$run" >/dev/null
docker run -d --name "$run-redis" --network "$run" --label com.centurylinklabs.watchtower.enable=false redis:7.4-alpine >/dev/null
docker run --rm --network "$run" --label com.centurylinklabs.watchtower.enable=false -v "$PWD/bot:/src:ro" \
  -e REDIS_TEST_URL="redis://$run-redis:6379/15" node:24.22.2-bookworm-slim sh -c \
  "cp -r /src /bot && cd /bot && rm -rf node_modules && npm ci --no-audit --no-fund >/dev/null 2>&1 && npx jest 2>&1 | tail -6"

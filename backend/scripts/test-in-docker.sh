#!/usr/bin/env sh
# Run the whole backend test suite in throwaway containers: a fresh pgvector database, an Anvil chain for
# the anchoring tests, a Redis for the job queue, and the API image with the test dependencies added.
# Nothing is published and everything is removed afterwards.
#   sh backend/scripts/test-in-docker.sh            (from the repository root)
#   IMAGE=clearhire-api:ci sh backend/scripts/...    (test an image already built, without rebuilding)
set -eu
run="clearhire-test-$$"
label="--label=com.centurylinklabs.watchtower.enable=false"
cleanup() {
  docker rm -f "$run-db" "$run-chain" "$run-redis" >/dev/null 2>&1 || true
  docker network rm "$run" >/dev/null 2>&1 || true
}
trap cleanup EXIT

image=${IMAGE:-clearhire-api:test}
[ -n "${IMAGE:-}" ] || docker build -q -f backend/Dockerfile -t "$image" . >/dev/null
docker network create "$run" >/dev/null
docker run -d --name "$run-db" --network "$run" "$label" \
  -e POSTGRES_USER=clearhire -e POSTGRES_PASSWORD=clearhire -e POSTGRES_DB=clearhire_test \
  pgvector/pgvector:0.8.0-pg17 >/dev/null
docker run -d --name "$run-chain" --network "$run" "$label" --entrypoint anvil \
  ghcr.io/foundry-rs/foundry:v1.8.6 --host 0.0.0.0 --silent >/dev/null
docker run -d --name "$run-redis" --network "$run" "$label" redis:7.4-alpine >/dev/null
until docker exec "$run-db" pg_isready -U clearhire -d clearhire_test >/dev/null 2>&1; do sleep 1; done

docker run --rm --network "$run" "$label" \
  -v "$PWD/backend/src:/app/src:ro" -v "$PWD/backend/tests:/app/tests:ro" -v "$PWD/backend/pyproject.toml:/app/pyproject.toml:ro" \
  -v "$PWD/contracts/test/fixtures:/contracts/test/fixtures:ro" \
  -e CLEARHIRE_TEST_DATABASE_URL="postgresql+asyncpg://clearhire:clearhire@$run-db:5432/clearhire_test" \
  -e ANVIL_URL="http://$run-chain:8545" -e REDIS_TEST_URL="redis://$run-redis:6379/0" \
  -e HOME=/tmp -e PYTHONPATH=/app/src -u root --entrypoint sh "$image" -c \
  "pip install -q --no-cache-dir pytest pytest-asyncio fakeredis faker reportlab >/dev/null 2>&1 && cd /app && python -m pytest -q -p no:cacheprovider $*"

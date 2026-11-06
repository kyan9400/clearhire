# syntax=docker/dockerfile:1.7
# The front door: Caddy with automatic HTTPS, serving the recruiter console (static Angular build) and
# routing the careers site and the API. Build from the repository root:
#   docker build -f deploy/caddy/Dockerfile -t clearhire-caddy .

FROM node:24.22.2-bookworm-slim AS console
WORKDIR /src/console
ENV NG_CLI_ANALYTICS=false
COPY console/package.json console/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY console ./
RUN npx ng build --configuration production

FROM caddy:2.10-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=console /src/console/dist/console/browser /srv/console

# syntax=docker/dockerfile:1.7
# The recruiter console on its own, for Kubernetes: the static Angular build behind unprivileged nginx on
# port 8080 (the Gateway terminates TLS and sends /api to the API). Build from the repository root:
#   docker build -f console/Dockerfile -t clearhire-console .
# The single-host deployment serves the same build from Caddy instead (deploy/caddy/Dockerfile).

FROM node:24.22.2-bookworm-slim AS build
WORKDIR /src/console
ENV NG_CLI_ANALYTICS=false
COPY console/package.json console/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY console ./
RUN npx ng build --configuration production

FROM nginxinc/nginx-unprivileged:1.31.7-alpine
COPY console/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY console/nginx/headers.conf /etc/nginx/snippets/headers.conf
COPY --from=build /src/console/dist/console/browser /usr/share/nginx/html
EXPOSE 8080

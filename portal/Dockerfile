# syntax=docker/dockerfile:1.7
# The careers site: Next.js standalone output on Node 24. Build from the repository root:
#   docker build -f portal/Dockerfile -t clearhire-portal .

FROM node:24.22.2-bookworm-slim AS build
WORKDIR /src/portal
ENV NEXT_TELEMETRY_DISABLED=1
COPY portal/package.json portal/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY api ../api
COPY portal ./
RUN npm run build

FROM node:24.22.2-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3100 HOSTNAME=0.0.0.0
COPY --from=build --chown=node /src/portal/.next/standalone ./
COPY --from=build --chown=node /src/portal/.next/static ./.next/static
USER node
EXPOSE 3100
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3100/how-we-hire').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]

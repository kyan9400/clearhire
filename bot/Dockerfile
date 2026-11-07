# syntax=docker/dockerfile:1.7
# The Telegram bot. Build from the repository root:
#   docker build -f bot/Dockerfile -t clearhire-bot .

FROM node:24.22.2-bookworm-slim AS build
WORKDIR /src/bot
COPY bot/package.json bot/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY bot ./
RUN npm run build && npm prune --omit=dev

FROM node:24.22.2-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node /src/bot/node_modules ./node_modules
COPY --from=build --chown=node /src/bot/dist ./dist
COPY --from=build --chown=node /src/bot/package.json ./
USER node
# no health check: the bot serves nothing, and a check that fails would get it restarted by autoheal
CMD ["node", "dist/main.js"]

# RuneTools web app: Fastify API + the built React UI, one Node process.
# Built by docker/docker-compose.yml (service "webapp"); context is webapp/.

FROM node:24-alpine AS build
RUN npm i -g pnpm@10.34.6
WORKDIR /src
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm --filter @runetools/web build \
 && pnpm --filter @runetools/api build \
 && pnpm --filter @runetools/api deploy --prod --legacy /out \
 && cp -r apps/web/dist /out/web

FROM node:24-alpine
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=8778 \
    WEB_DIST=/app/web \
    MIGRATIONS_DIR=/app/drizzle
WORKDIR /app
COPY --from=build /out/package.json ./
COPY --from=build /out/node_modules ./node_modules
COPY --from=build /out/dist ./dist
COPY --from=build /out/drizzle ./drizzle
COPY --from=build /out/web ./web
USER node
EXPOSE 8778
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD wget -qO- http://127.0.0.1:8778/api/health || exit 1
CMD ["node", "dist/server.js"]

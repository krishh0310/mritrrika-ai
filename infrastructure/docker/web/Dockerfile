# The Next.js web application (§75).
#
# Multi-stage: the final image carries the standalone build output and node_modules
# it actually needs, not the toolchain that produced them.

FROM node:22-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/
COPY apps/mobile/package.json ./apps/mobile/
COPY packages/ui/package.json ./packages/ui/
COPY packages/shared-types/package.json ./packages/shared-types/
# The mobile workspace is not needed to build the web app and pulls in the
# whole Expo toolchain.
RUN npm ci --workspace @mrittika/web --workspace @mrittika/ui \
      --workspace @mrittika/shared-types --include-workspace-root

FROM node:22-alpine AS build
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY packages ./packages
COPY apps/web ./apps/web
# Baked into the bundle at build time, so it must be supplied as a build arg.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build --workspace @mrittika/web

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -g 10001 mrittika && adduser -S -u 10001 -G mrittika mrittika

COPY --from=build /repo/apps/web/.next ./.next
# MapLibre's worker, copied there by the prebuild step (see parcel-map.tsx).
COPY --from=build /repo/apps/web/public ./public
COPY --from=build /repo/apps/web/package.json ./package.json
COPY --from=build /repo/node_modules ./node_modules

USER mrittika
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=25s --retries=5 \
  CMD wget -qO- http://localhost:3000/ >/dev/null || exit 1

CMD ["npx", "next", "start", "--port", "3000", "--hostname", "0.0.0.0"]

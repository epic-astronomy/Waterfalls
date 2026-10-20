# The Waterfalls website (Nuxt). Built here, then only the server bundle is
# kept. Settings are read at run time from NUXT_* variables:
#   NUXT_API_ORIGIN             the FastAPI backend that /api/v1 is passed to
#   NUXT_PUBLIC_HANKO_API_URL   the Hanko project
#   NUXT_PUBLIC_SITE_URL        the canonical origin
FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-fund --no-audit
COPY . .
RUN npx nuxt prepare && npx nuxt build

FROM node:24-slim
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]

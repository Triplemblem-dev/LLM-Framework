# Matches the Node version already validated locally (see `node -v`) rather
# than jumping to a newer major untested against this codebase.
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* variables are inlined into the client bundle at build time,
# not read at container start - must be supplied as a build arg.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
# next.config.mjs sets output: "standalone" - .next/standalone already
# contains only the node_modules files actually needed at runtime, so the
# full node_modules tree from the build stage is never copied here.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]

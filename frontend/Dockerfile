FROM node:20-alpine AS base

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

FROM base AS builder

# The lockfile is copied separately so that the dependency layer is cached
# and is only invalidated when the dependencies actually change.
COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml* ./
RUN pnpm install --no-frozen-lockfile

COPY . .
# `output: "standalone"` in next.config.mjs produces the server bundle that
# the runner stage copies. The flag is opt-in so that a local Windows build
# is not blocked by the pnpm symlink recreation.
ENV NEXT_OUTPUT_STANDALONE=true
RUN pnpm build

FROM base AS runner

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Run as an unprivileged user.
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD wget --spider -q http://localhost:3000 || exit 1

CMD ["node", "server.js"]

FROM node:20-bookworm-slim

# build tools for node-pty; python + git because the GHL CLI and Claude both want them
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip build-essential git curl ca-certificates openssh-client less \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

# run as a normal user, never root
RUN useradd -m -s /bin/bash gf && mkdir -p /app /workspace /uploads && chown -R gf:gf /app /workspace /uploads
USER gf
WORKDIR /app

COPY --chown=gf:gf package.json package-lock.json ./
RUN npm ci --omit=dev
COPY --chown=gf:gf server ./server
COPY --chown=gf:gf public ./public
COPY --chown=gf:gf skills ./skills

ENV PORT=3100 WORKDIR=/workspace UPLOAD_DIR=/uploads COOKIE_SECURE=1 NODE_ENV=production
EXPOSE 3100
CMD ["node", "server/index.js"]

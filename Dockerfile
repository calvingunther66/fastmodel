# Single image that runs the FastAPI app AND the cloudflared tunnel daemon.
#
# Stage 1 builds the React frontend; stage 2 is the Python runtime with
# cloudflared added. An entrypoint runs uvicorn + cloudflared together.
#
# Build (on the Pi, which is arm64):  docker build -t schedule .
# BuildKit sets TARGETARCH automatically (arm64 on a 64-bit Pi, amd64 on x86).

# ---- Stage 1: build the web frontend -------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build              # -> /web/dist

# ---- Stage 2: python runtime + cloudflared -------------------------------
FROM python:3.12-slim AS runtime

# cloudflared (architecture-matched) + tini for clean signal handling
ARG TARGETARCH
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tini \
 && curl -fsSL -o /usr/local/bin/cloudflared \
      "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${TARGETARCH}" \
 && chmod +x /usr/local/bin/cloudflared \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (core extractor + server)
COPY requirements.txt ./requirements.txt
COPY server/requirements.txt ./server-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r server-requirements.txt

# Application code + built frontend
COPY schedule_extractor/ ./schedule_extractor/
COPY server/ ./server/
COPY --from=web /web/dist ./web/dist
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Server defaults; override at runtime. Data persists in a mounted volume.
ENV HOST=0.0.0.0 \
    PORT=8000 \
    DATA_DIR=/data \
    TIMEZONE=America/Los_Angeles \
    SESSION_HTTPS_ONLY=true
VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]

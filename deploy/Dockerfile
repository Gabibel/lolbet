# Optional. On a Raspberry Pi or an Oracle Cloud Always Free ARM VM you do not
# need this at all - the systemd unit in this directory is simpler and lighter.
# Kept for people who already run everything in containers.
#
#   docker build -f deploy/Dockerfile -t lolbet .
#   docker run -d --name lolbet --restart unless-stopped \
#       --env-file .env -v "$PWD/data:/data" lolbet
#
# Multi-arch (builds an arm64 image for a Pi 4/5 or an Ampere A1 VM):
#   docker buildx build --platform linux/arm64 -f deploy/Dockerfile -t lolbet .

FROM python:3.12-slim-bookworm AS builder

WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir .


FROM python:3.12-slim-bookworm

# Non-root, and a data directory it owns. Everything else stays read-only.
RUN useradd --system --create-home --uid 10001 lolbet \
    && mkdir -p /data \
    && chown lolbet:lolbet /data

COPY --from=builder /venv /venv

ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOLBET_DATABASE_URL="sqlite+aiosqlite:////data/lolbet.db" \
    LOLBET_LOG_JSON=true

USER lolbet
WORKDIR /data
VOLUME ["/data"]

# No ports: the bot dials out to Discord over a websocket, nothing dials in.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sqlite3,sys; sqlite3.connect('/data/lolbet.db').close()" || exit 1

ENTRYPOINT ["python", "-m", "lolbet"]

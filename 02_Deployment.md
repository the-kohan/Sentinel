# 02 Deployment — As Built

> **Source:** Live `Dockerfile`, `docker-compose.yaml`, `sentinel/sentinel.env`  
> **Purpose:** Rebuild the container and run it.

---

## Dockerfile

```dockerfile
# Sentinel Network Guard - Containerized Analyzer
# Multi-stage build for minimal production image

# Build stage
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim-bookworm

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Ensure local packages are on PATH
ENV PATH=/root/.local/bin:$PATH

# Copy source code as Python packages
COPY src/ /app/src/
COPY sentinel/ /app/sentinel/
COPY collectors/ /app/collectors/

# Create collector data directory (bind-mounted from host)
RUN mkdir -p /data/collector

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8100/status || exit 1

EXPOSE 8100

# Default command - run the analyzer
CMD ["uvicorn", "src.analyzer:app", "--host", "0.0.0.0", "--port", "8100"]
```

---

## Requirements

```text
fastapi==0.115.6
uvicorn[standard]==0.34.2
psycopg2-binary==2.9.10
docker==7.1.0
requests==2.32.3
python-multipart==0.0.20
python-dotenv==1.0.1
```

---

## Docker Compose Entry

```yaml
  sentinel:
    build:
      context: E:\kohanastack\sentinel
      dockerfile: Dockerfile
    container_name: sentinel
    hostname: sentinel
    networks:
      - kohana
    ports:
      - "127.0.0.1:8100:8100"
    env_file:
      - .env
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=Kohan
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=${REDIS_PASSWORD}
      - OLLAMA_URL=http://ollama:11434
      - OPENCLAW_GATEWAY_URL=http://openclaw:18789
      - OPENCLAW_HOOK_TOKEN=${SENTINEL_HOOK_TOKEN}
      - TZ=${TZ}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./sentinel/collector-data:/data/collector
    deploy:
      resources:
        limits:
          memory: 512M
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      openclaw:
        condition: service_started
```

---

## Environment Variables

**From `.env` (main compose):**

| Variable | Used By | Purpose |
|---|---|---|
| `POSTGRES_USER` | Sentinel | Postgres username |
| `POSTGRES_PASSWORD` | Sentinel | Postgres password |
| `SENTINEL_HOOK_TOKEN` | Sentinel | Bearer token for OpenClaw webhook |
| `TZ` | Sentinel | Timezone (`Africa/Nairobi`) |

**From `sentinel/sentinel.env` (inside container):**

| Variable | Purpose |
|---|---|
| `TELEGRAM_TOKEN` | Fallback Telegram bot token |
| `TELEGRAM_CHAT_ID` | Fallback Telegram chat target |
| `POSTGRES_USER` | Default: `Kohan` |
| `POSTGRES_PASSWORD` | Default: empty |
| `POSTGRES_DB` | Default: `sentinel_db` |
| `POSTGRES_HOST` | Default: `127.0.0.1` |
| `POSTGRES_PORT` | Default: `5432` |
| `SENTINEL_ROOT` | Root path for scripts |
| `SENTINEL_HOOK_TOKEN` | OpenClaw hook token |

**Note:** `TELEGRAM_TOKEN` is currently a placeholder and needs a real bot token for fallback delivery to work.

---

## Build & Run Commands

```bash
# Build image
docker-compose -f E:/kohanastack/docker-compose.yaml build sentinel

# Start
docker-compose -f E:/kohanastack/docker-compose.yaml up -d sentinel

# Verify
curl http://127.0.0.1:8100/status

# Logs
docker logs sentinel --tail 50
```

---

## Source Files Required

| Path | Purpose |
|---|---|
| `src/__init__.py` | Package marker |
| `src/analyzer.py` | FastAPI app + background loop |
| `src/db.py` | Postgres access layer |
| `src/notifier.py` | Alert delivery |
| `src/api.py` | Legacy API (not deployed) |
| `src/main.py` | Legacy loop (not deployed) |
| `collectors/host_collector.py` | Standalone host collector |
| `collectors/docker_collector.py` | Standalone Docker collector |
| `sentinel/__init__.py` | Package marker |
| `sentinel/scripts/alert.sh` | Telegram router |
| `sentinel/scripts/db.sh` | Postgres helper |
| `sentinel/scripts/sentinel.sh` | Legacy shell loop |
| `sentinel/sentinel.env` | Env vars for scripts |

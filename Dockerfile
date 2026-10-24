# Sentinel Network Guard - Containerized Analyzer + Dashboard
# Single container: FastAPI backend + static Next.js dashboard on one port

# ── Build stage: compile the dashboard ──────────────────────────────
FROM node:22-slim AS dashboard-builder

WORKDIR /build

# node:22-slim already bundles npm (10.9.9) — no apt-get needed. The previous
# apt-get install npm + npm install -g npm@10 pair cost ~20 minutes per build
# and made every dashboard rebuild depend on Debian mirror reachability.

# Copy dashboard source and build
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --production=false

COPY dashboard/ ./
# Build via node directly — bypasses .bin wrapper shebang issue
RUN node node_modules/next/dist/bin/next build

# ── Python build stage ──────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS python-builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Runtime stage ───────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copy Python packages from builder
COPY --from=python-builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy source code
COPY src/ /app/src/
COPY sentinel/ /app/sentinel/
COPY collectors/ /app/collectors/

# Copy built dashboard (static HTML + JS/CSS bundles)
COPY --from=dashboard-builder /build/.next /app/dashboard/.next
# Public folder may not exist — copy only if present
COPY --from=dashboard-builder /build/public /app/dashboard/public

# Create collector data directory (bind-mounted from host)
RUN mkdir -p /data/collector

# Health check (hits the API endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8100/api/status || exit 1

EXPOSE 8100

# Start FastAPI — it serves the dashboard static files on the same port
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8100"]

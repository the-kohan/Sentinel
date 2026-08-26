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
# Multi-stage build for PlatformContextGraph
FROM python:3.12-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies required for building
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Go builder stage
FROM golang:1.26-alpine AS go-builder

WORKDIR /build

# Copy Go module files and download dependencies
COPY go/go.mod go/go.sum ./go/
RUN cd go && go mod download

# Copy Go source
COPY go/ ./go/

# Build all Go binaries
RUN cd go && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-ingester ./cmd/ingester \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-bootstrap-index ./cmd/bootstrap-index \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-reducer ./cmd/reducer \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-projector ./cmd/projector \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-collector-git ./cmd/collector-git \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-bootstrap-data-plane ./cmd/bootstrap-data-plane \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-admin-status ./cmd/admin-status

# Production stage
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies.
# - git is required for repo sync operations
# - curl is used by the container healthcheck
# - gh is retained for optional clone flows used elsewhere in the CLI
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/pcg /usr/local/bin/pcg

# Copy source code
COPY --from=builder /app/src /app/src

# Copy Go binaries from go-builder
COPY --from=go-builder /go-bin/ /usr/local/bin/

# Create the runtime user and writable working directories.
RUN useradd --create-home --uid 10001 --user-group pcg \
    && mkdir -p /workspace /data/.platform-context-graph \
    && chown -R pcg:pcg /app /workspace /data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOME=/data
ENV PCG_HOME=/data/.platform-context-graph

# Remote FalkorDB connection (set at runtime via docker run -e or docker-compose)
# ENV DATABASE_TYPE=falkordb-remote
# ENV FALKORDB_HOST=
# ENV FALKORDB_PORT=6379
# ENV FALKORDB_PASSWORD=
# ENV FALKORDB_USERNAME=
# ENV FALKORDB_SSL=false
# ENV FALKORDB_GRAPH_NAME=codegraph

# Expose the combined service port
EXPOSE 8080

# Default working directory for repo data
WORKDIR /data
USER pcg

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

# Default command - run the combined HTTP API and MCP service
CMD ["pcg", "serve", "start", "--host", "0.0.0.0", "--port", "8080"]

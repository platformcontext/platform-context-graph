# Multi-stage build for PlatformContextGraph (Go-only)
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache git

WORKDIR /build

# Copy Go module files and download dependencies
COPY go/go.mod go/go.sum ./go/
RUN cd go && go mod download

# Copy Go source
COPY go/ ./go/

# Build all Go binaries
RUN cd go && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg ./cmd/pcg \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-api ./cmd/api \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-mcp-server ./cmd/mcp-server \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-ingester ./cmd/ingester \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-bootstrap-index ./cmd/bootstrap-index \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-reducer ./cmd/reducer \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-projector ./cmd/projector \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-collector-git ./cmd/collector-git \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-bootstrap-data-plane ./cmd/bootstrap-data-plane \
    && CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /go-bin/pcg-admin-status ./cmd/admin-status

# Production stage
FROM alpine:3.21

RUN apk add --no-cache git curl

# Copy Go binaries
COPY --from=builder /go-bin/ /usr/local/bin/

# Create the runtime user and writable working directories.
RUN adduser -D -u 10001 pcg \
    && mkdir -p /workspace /data/.platform-context-graph \
    && chown -R pcg:pcg /workspace /data

ENV HOME=/data
ENV PCG_HOME=/data/.platform-context-graph

# Expose the combined service port
EXPOSE 8080

WORKDIR /data
USER pcg

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

# Default command - run the Go API server
CMD ["pcg-api"]

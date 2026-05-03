#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GO_DIR="$REPO_ROOT/go"

if [[ -z "${GOBIN:-}" ]]; then
    GOPATH_VALUE="$(go env GOPATH)"
    if [[ -z "$GOPATH_VALUE" ]]; then
        echo "go env GOPATH returned an empty value; set GOBIN and retry." >&2
        exit 1
    fi
    INSTALL_DIR="$GOPATH_VALUE/bin"
else
    INSTALL_DIR="$GOBIN"
fi

mkdir -p "$INSTALL_DIR"

VERSION="${PCG_VERSION:-dev}"
LDFLAGS="-X github.com/platformcontext/platform-context-graph/go/internal/buildinfo.Version=${VERSION}"

cd "$GO_DIR"

go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg" ./cmd/pcg
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-api" ./cmd/api
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-mcp-server" ./cmd/mcp-server
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-bootstrap-index" ./cmd/bootstrap-index
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-ingester" ./cmd/ingester
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-reducer" ./cmd/reducer
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-workflow-coordinator" ./cmd/workflow-coordinator
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-projector" ./cmd/projector
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-collector-git" ./cmd/collector-git
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-bootstrap-data-plane" ./cmd/bootstrap-data-plane
go build -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg-admin-status" ./cmd/admin-status

echo "Installed PCG binaries to $INSTALL_DIR"
echo "Make sure this directory is on PATH before running pcg graph start or pcg doctor."

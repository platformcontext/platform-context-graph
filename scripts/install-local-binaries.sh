#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GO_DIR="$REPO_ROOT/go"

resolve_install_dir() {
    if [[ -n "${GOBIN:-}" ]]; then
        printf '%s\n' "$GOBIN"
        return
    fi

    local gopath_value
    local first_gopath
    gopath_value="$(go env GOPATH)"
    if [[ -z "$gopath_value" ]]; then
        echo "go env GOPATH returned an empty value; set GOBIN and retry." >&2
        exit 1
    fi

    IFS=':' read -r first_gopath _ <<< "$gopath_value"
    if [[ -z "$first_gopath" ]]; then
        echo "go env GOPATH did not include a usable first path; set GOBIN and retry." >&2
        exit 1
    fi

    printf '%s/bin\n' "$first_gopath"
}

main() {
    INSTALL_DIR="$(resolve_install_dir)"

    mkdir -p "$INSTALL_DIR"

    VERSION="${PCG_VERSION:-dev}"
    LDFLAGS="-X github.com/platformcontext/platform-context-graph/go/internal/buildinfo.Version=${VERSION}"
    PCG_BUILD_TAGS="${PCG_LOCAL_OWNER_BUILD_TAGS-nolocalllm}"
    PCG_BUILD_TAG_ARGS=()
    if [[ -n "$PCG_BUILD_TAGS" ]]; then
        PCG_BUILD_TAG_ARGS=(-tags "$PCG_BUILD_TAGS")
    fi

    cd "$GO_DIR"

    go build "${PCG_BUILD_TAG_ARGS[@]}" -trimpath -ldflags="$LDFLAGS" -o "$INSTALL_DIR/pcg" ./cmd/pcg
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
    if [[ -n "$PCG_BUILD_TAGS" ]]; then
        echo "Built local owner pcg with Go tags: $PCG_BUILD_TAGS"
    fi
    echo "Make sure this directory is on PATH before running pcg graph start or pcg doctor."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

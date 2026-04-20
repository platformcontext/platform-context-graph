#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CONFIG_FILE="$TMP_DIR/mcp.json"

cat >"$CONFIG_FILE" <<'EOF'
{
  "mcpServers": {
    "pcg-e2e": {
      "type": "http",
      "url": "http://10.0.0.5:8081/mcp/message",
      "headers": {
        "Authorization": "Bearer remote-token"
      }
    }
  }
}
EOF

PCG_MCP_CONFIG_FILE="$CONFIG_FILE" \
PCG_LOCAL_MCP_URL="http://127.0.0.1:18081/mcp/message" \
PCG_LOCAL_MCP_TOKEN="local-token-1" \
PCG_SKIP_PROBES="true" \
"$REPO_ROOT/scripts/sync_local_compose_mcp.sh"

jq -e '
  .mcpServers["pcg-e2e"].url == "http://10.0.0.5:8081/mcp/message" and
  .mcpServers["pcg-e2e"].headers.Authorization == "Bearer remote-token" and
  .mcpServers["pcg-local-compose"].type == "http" and
  .mcpServers["pcg-local-compose"].url == "http://127.0.0.1:18081/mcp/message" and
  .mcpServers["pcg-local-compose"].headers.Authorization == "Bearer local-token-1"
' "$CONFIG_FILE" >/dev/null

PCG_MCP_CONFIG_FILE="$CONFIG_FILE" \
PCG_LOCAL_MCP_URL="http://127.0.0.1:28081/mcp/message" \
PCG_LOCAL_MCP_TOKEN="local-token-2" \
PCG_SKIP_PROBES="true" \
"$REPO_ROOT/scripts/sync_local_compose_mcp.sh"

jq -e '
  (.mcpServers | keys | sort) == ["pcg-e2e", "pcg-local-compose"] and
  .mcpServers["pcg-e2e"].url == "http://10.0.0.5:8081/mcp/message" and
  .mcpServers["pcg-e2e"].headers.Authorization == "Bearer remote-token" and
  .mcpServers["pcg-local-compose"].url == "http://127.0.0.1:28081/mcp/message" and
  .mcpServers["pcg-local-compose"].headers.Authorization == "Bearer local-token-2"
' "$CONFIG_FILE" >/dev/null

echo "sync_local_compose_mcp test passed"

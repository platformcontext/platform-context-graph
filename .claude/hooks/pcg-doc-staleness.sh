#!/usr/bin/env bash
# .claude/hooks/pcg-doc-staleness.sh
#
# Claude Code PostToolUse hook (matcher: Edit|Write).
# Reads the tool input JSON from stdin, extracts the file_path, and delegates
# to scripts/check-docs-stale.sh so Claude Code and Codex use the same check.

set -u
set -o pipefail

# Drain stdin so Claude Code doesn't block on a closed pipe.
cat >/dev/null

repo_root="${CLAUDE_PROJECT_DIR:-}"
[ -z "$repo_root" ] && repo_root="$(git rev-parse --show-toplevel 2>/dev/null \
  || (cd "$(dirname "$0")/../.." && pwd))"

# --all rebuilds the full drift snapshot. Same call shape as the Codex hook so
# both tools converge on the same .pcg-doc-state/stale.jsonl content.
PCG_DOC_KEEPER_TOOL=claude-code \
  "$repo_root/scripts/check-docs-stale.sh" --all

exit 0

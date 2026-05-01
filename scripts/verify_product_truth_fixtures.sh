#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$REPO_ROOT/tests/fixtures/product_truth/manifest.json"

require_file() {
    local path="$1"
    [[ -f "$path" ]] || {
        echo "Missing required file: $path" >&2
        return 1
    }
}

require_dir() {
    local path="$1"
    [[ -d "$path" ]] || {
        echo "Missing required directory: $path" >&2
        return 1
    }
    [[ ! -L "$path" ]] || {
        echo "Fixture directory must not be a symlink: $path" >&2
        return 1
    }
}

require_executable() {
    local path="$1"
    [[ -x "$path" ]] || {
        echo "Expected executable verifier: $path" >&2
        return 1
    }
}

require_json_query() {
    local file="$1"
    local query="$2"
    local description="$3"
    jq -e "$query" "$file" >/dev/null || {
        echo "$description" >&2
        echo "File: $file" >&2
        return 1
    }
}

require_file "$MANIFEST"
require_json_query "$MANIFEST" '.schema_version == 1' "Product truth manifest schema_version must be 1"
require_json_query "$MANIFEST" '(.suites // []) | length >= 3' "Product truth manifest must register owned fixture suites"
require_json_query "$MANIFEST" '(.planned // []) | any(.id == "iac_quality.dead_iac" and .status == "planned")' \
    "Product truth manifest must track the planned dead-IaC capability"

while IFS= read -r suite; do
    id="$(jq -r '.id' <<<"$suite")"
    status="$(jq -r '.status' <<<"$suite")"
    fixture_root="$REPO_ROOT/$(jq -r '.fixture_root' <<<"$suite")"
    compose_gate="$REPO_ROOT/$(jq -r '.compose_gate' <<<"$suite")"

    if [[ "$status" != "owned" ]]; then
        echo "Skipping non-owned suite $id ($status)"
        continue
    fi

    require_dir "$fixture_root"
    require_executable "$compose_gate"
    require_json_query <(printf '%s' "$suite") '(.capabilities // []) | length > 0' \
        "Suite $id must list capabilities"
    require_json_query <(printf '%s' "$suite") '(.expected_truth_files // []) | length > 0' \
        "Suite $id must list expected truth files"

    while IFS= read -r expected_file; do
        expected_path="$REPO_ROOT/$expected_file"
        require_file "$expected_path"
        case "$expected_path" in
            *.json)
                require_json_query "$expected_path" '.schema_version == 1' \
                    "Expected truth file must declare schema_version=1: $expected_file"
                require_json_query "$expected_path" '(.capability_assertions // []) | length > 0' \
                    "Expected truth file must include capability assertions: $expected_file"
                ;;
            *.yaml|*.yml)
                # Existing fixture contracts may be YAML. Their runtime verifier
                # owns semantic validation; this static gate only checks presence.
                ;;
            *)
                echo "Unsupported expected truth file type: $expected_file" >&2
                exit 1
                ;;
        esac
    done < <(jq -r '.expected_truth_files[]' <<<"$suite")

    echo "verified product truth suite: $id"
done < <(jq -c '.suites[]' "$MANIFEST")

require_file "$REPO_ROOT/tests/fixtures/product_truth/planned/dead_iac_cases.json"
require_json_query "$REPO_ROOT/tests/fixtures/product_truth/planned/dead_iac_cases.json" \
    '.capability == "iac_quality.dead_iac" and .status == "planned" and ((.families // []) | length) == 3' \
    "Dead-IaC planned contract must cover Terraform, Helm, and Ansible families"

echo "Product truth fixture contract verified."


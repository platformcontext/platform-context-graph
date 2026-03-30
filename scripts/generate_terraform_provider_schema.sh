#!/usr/bin/env bash
#
# Generate Terraform provider schemas for resource-type auto-discovery.
#
# Usage:
#   ./scripts/generate_terraform_provider_schema.sh          # all providers
#   ./scripts/generate_terraform_provider_schema.sh aws      # specific provider
#
# Prerequisites:
#   - terraform CLI installed (https://developer.hashicorp.com/terraform/install)
#
# Output:
#   schemas/<provider>.json  (raw, gitignored)
#
# The generated JSON is consumed by the Python schema loader at
# src/platform_context_graph/relationships/terraform_evidence/provider_schema.py

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROVIDERS_DIR="$REPO_ROOT/terraform_providers"
SCHEMAS_DIR="$REPO_ROOT/schemas"

mkdir -p "$SCHEMAS_DIR"

generate_schema() {
    local provider="$1"
    local provider_dir="$PROVIDERS_DIR/$provider"

    if [[ ! -d "$provider_dir" ]]; then
        echo "ERROR: No provider config at $provider_dir" >&2
        return 1
    fi

    echo "==> Generating schema for provider: $provider"

    cd "$provider_dir"

    echo "    terraform init..."
    terraform init -input=false -no-color >/dev/null 2>&1

    echo "    terraform providers schema -json..."
    terraform providers schema -json > "$SCHEMAS_DIR/$provider.json"

    local resource_count
    resource_count=$(python3 -c "
import json, sys
with open('$SCHEMAS_DIR/$provider.json') as f:
    schema = json.load(f)
for ps in schema.get('provider_schemas', {}).values():
    print(len(ps.get('resource_schemas', {})))
    sys.exit()
print(0)
")

    local file_size
    file_size=$(du -h "$SCHEMAS_DIR/$provider.json" | cut -f1)

    echo "    Done: $resource_count resource types, $file_size"
    echo "    Output: $SCHEMAS_DIR/$provider.json"
    echo ""
}

# Determine which providers to generate.
if [[ $# -gt 0 ]]; then
    providers=("$@")
else
    providers=()
    for dir in "$PROVIDERS_DIR"/*/; do
        [[ -d "$dir" ]] && providers+=("$(basename "$dir")")
    done
fi

if [[ ${#providers[@]} -eq 0 ]]; then
    echo "No provider directories found in $PROVIDERS_DIR" >&2
    exit 1
fi

for provider in "${providers[@]}"; do
    generate_schema "$provider"
done

echo "Schema generation complete. Files in $SCHEMAS_DIR/"
echo ""
echo "Next steps:"
echo "  1. Verify: python3 -c \"import json; s=json.load(open('schemas/aws.json')); print(len(list(s['provider_schemas'].values())[0]['resource_schemas']), 'resource types')\""
echo "  2. Package for distribution: ./scripts/package_terraform_schemas.sh"
echo "  3. Run tests: PYTHONPATH=src uv run python -m pytest tests/unit/relationships/test_terraform_provider_schema.py -v"

# .pcgignore Guide

The `.pcgignore` file tells PlatformContextGraph which files or folders to skip during indexing. It uses `.gitignore`-style patterns and is the right tool for project-specific exclusions.

## What PCG already ignores

You do not need to add common cache trees just to protect the indexer from them. PCG already prunes hidden and configured cache directories before descent, including:

- `.git/`
- `.terraform/`
- `.terragrunt-cache/`
- `.terramate-cache/`
- `.pulumi/`
- `.crossplane/`
- `.serverless/`
- `.aws-sam/`
- `cdk.out/`

It also skips other common dependency and build directories such as `node_modules/`, `dist/`, `build/`, `target/`, `.venv/`, and `__pycache__/` through the default `IGNORE_DIRS` configuration.

Use `.pcgignore` for repo-local choices that are specific to your project, team, or indexing goals.

## Why use it?

- **Performance:** Skip large generated trees that are not part of the code or infrastructure you want to analyze.
- **Relevance:** Keep the graph focused on the source, manifests, and configuration that matter.
- **Privacy:** Exclude local secrets, generated configs, or internal-only documents from the graph.

## File Specification

- **Filename:** `.pcgignore`
- **Location:** Place it at the root of the repository or mono-folder you index.
- **Syntax:** Standard `.gitignore`-style glob patterns.

When PCG indexes a directory, it walks upward to find the nearest `.pcgignore` and applies patterns relative to that file.

## Recommended Example

Create a file named `.pcgignore` in your project root with content like this:

```text
# Application dependencies and local environments
node_modules/
venv/
.venv/
__pycache__/

# Build and coverage artifacts
dist/
build/
target/
coverage/
htmlcov/
*.egg-info/

# Optional: skip tests if you only want runtime code and IaC
tests/
spec/
**/*_test.py
**/*.test.js

# Project-specific generated files
docs/site/
generated/
tmp/
fixtures/output/

# Secrets and local-only config
.env
*.pem
secrets.json
terraform.tfstate
terraform.tfstate.backup
```

## IaC Note

If you work in Terraform, Terragrunt, Pulumi, Crossplane, CDK, or serverless repos, PCG already avoids the major local cache and build directories listed above. Add `.pcgignore` entries only for files that are valid repo content but still not useful to index, such as generated manifests, rendered templates, or local state files.

## Related docs

- [CLI: Indexing & Management](cli-indexing.md)
- [Configuration & Settings](configuration.md)
- [Troubleshooting](troubleshooting.md)

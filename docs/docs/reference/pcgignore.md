# .pcgignore Guide

The `.pcgignore` file tells PlatformContextGraph which files or folders to skip
during indexing. It uses `.gitignore`-style patterns and is the right tool for
project-specific exclusions.

## What PCG already ignores

You do not need to add common cache trees just to protect the indexer from them.
PCG already prunes hidden and configured cache directories before descent,
including:

- `.git/`
- `.terraform/`
- `.terragrunt-cache/`
- `.terramate-cache/`
- `.pulumi/`
- `.crossplane/`
- `.serverless/`
- `.aws-sam/`
- `cdk.out/`

PCG also excludes built-in dependency roots before parse when
`PCG_IGNORE_DEPENDENCY_DIRS=true`:

- JavaScript and TypeScript: `node_modules/`, `bower_components/`,
  `jspm_packages/`
- Python: `site-packages/`, `dist-packages/`, `__pypackages__/`
- PHP and Go: `vendor/`
- Ruby: `vendor/bundle/`
- Elixir: `deps/`
- Swift ecosystem: `Carthage/Checkouts/`, `.build/checkouts/`, `Pods/`

These directories do not enter checkpoints, Neo4j, Postgres, or finalization.
If you need dependency internals, load them explicitly with a `.pcg` bundle
instead of relying on routine repo indexing.

Use `.pcgignore` for repo-local choices that are specific to your project, team, or indexing goals.

## `.gitignore` Interaction

PCG also honors the target repository's own `.gitignore` files during repo and
workspace indexing by default (`PCG_HONOR_GITIGNORE=true`).

- Only `.gitignore` files inside the target repo are used.
- Parent workspace `.gitignore` files do not leak into sibling repos.
- Nested `.gitignore` files inside the repo still apply within their subtree.
- Matching files are hard-excluded from repo/workspace ingest.

This means `.gitignore` is still useful for repo-local generated or published
assets, while `.pcgignore` remains the PCG-specific override for additional
indexing choices. Dependency trees no longer need `.gitignore` or `.pcgignore`
entries just to keep them out of the default index.

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

If you work in Terraform, Terragrunt, Pulumi, Crossplane, CDK, or serverless
repos, PCG already avoids the major local cache and build directories listed
above. Add `.pcgignore` entries only for files that are valid repo content but
still not useful to index, such as generated manifests, rendered templates, or
local state files.

## Related docs

- [CLI: Indexing & Management](cli-indexing.md)
- [Configuration & Settings](configuration.md)
- [Troubleshooting](troubleshooting.md)

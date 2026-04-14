# Parser Support Maturity Matrix

This page tracks the checked-in Go parser support-maturity matrix for this branch.

This matrix is intentionally coarse. It does not replace the branch-level parity
audit or the per-language capability pages.

Use:

- [Python-To-Go Parity Audit](../reference/python-to-go-parity.md) for the
  current branch closure bar
- the language pages under `docs/docs/languages/` for exact partial or
  unsupported capability details

This matrix tracks the higher-level support bar for each parser beyond
the raw capability checklist. `-` means that maturity dimension has not
yet been explicitly assessed in the parser maturity program.

| Parser | Parser Class | Grammar Routing | Normalization | Framework Packs | Pack Names | Query Surfacing | Real-Repo Validation | End-to-End Indexing |
|--------|--------------|-----------------|---------------|-----------------|------------|-----------------|----------------------|---------------------|
| ArgoCD | `DefaultEngine (yaml)` | - | - | - | - | - | - | - |
| C | `DefaultEngine (c)` | - | - | - | - | - | - | - |
| CloudFormation | `DefaultEngine (yaml)` | - | - | - | - | - | - | - |
| C++ | `DefaultEngine (cpp)` | - | - | - | - | - | - | - |
| Crossplane | `DefaultEngine (yaml)` | - | - | - | - | - | - | - |
| C# | `DefaultEngine (c_sharp)` | - | - | - | - | - | - | - |
| Dart | `DefaultEngine (dart)` | - | - | - | - | - | - | - |
| Elixir | `DefaultEngine (elixir)` | - | - | - | - | - | - | - |
| Go | `DefaultEngine (go)` | - | - | - | - | - | - | - |
| Groovy | `DefaultEngine (groovy)` | - | - | - | - | - | - | - |
| Haskell | `DefaultEngine (haskell)` | - | - | - | - | - | - | - |
| Helm | `DefaultEngine (yaml)` | - | - | - | - | - | - | - |
| Java | `DefaultEngine (java)` | - | - | - | - | - | - | - |
| JavaScript | `DefaultEngine (javascript)` | supported | supported | supported | `react-base`, `nextjs-app-router-base`, `express-base`, `hapi-base`, `aws-sdk-base`, `gcp-sdk-base` | supported | supported | supported |
| JSON Config | `DefaultEngine (json)` | - | - | - | - | - | - | - |
| Kotlin | `DefaultEngine (kotlin)` | - | - | - | - | - | - | - |
| Kubernetes | `DefaultEngine (yaml)` | - | - | - | - | - | - | - |
| Kustomize | `DefaultEngine (yaml)` | - | - | - | - | - | - | - |
| Perl | `DefaultEngine (perl)` | - | - | - | - | - | - | - |
| PHP | `DefaultEngine (php)` | - | - | - | - | - | - | - |
| Python | `DefaultEngine (python)` | supported | supported | supported | `fastapi-base`, `flask-base` | supported | supported | supported |
| Ruby | `DefaultEngine (ruby)` | - | - | - | - | - | - | - |
| Rust | `DefaultEngine (rust)` | - | - | - | - | - | - | - |
| Scala | `DefaultEngine (scala)` | - | - | - | - | - | - | - |
| SQL | `DefaultEngine (sql)` | supported | supported | unsupported | - | supported | partial | partial |
| Swift | `DefaultEngine (swift)` | - | - | - | - | - | - | - |
| Terraform | `DefaultEngine (hcl)` | - | - | - | - | - | - | - |
| Terragrunt | `DefaultEngine (hcl)` | - | - | - | - | - | - | - |
| TypeScript | `DefaultEngine (typescript)` | supported | supported | supported | `react-base`, `nextjs-app-router-base`, `express-base`, `hapi-base`, `aws-sdk-base`, `gcp-sdk-base` | supported | supported | supported |
| TypeScript JSX | `DefaultEngine (tsx)` | supported | supported | supported | `react-base`, `nextjs-app-router-base` | supported | supported | supported |

# Argo CD

Argo CD examples live under:

- `deploy/argocd/base`
- `deploy/argocd/overlays/aws`

Recommended layout:
- cloud-neutral base application
- AWS overlay for External Secrets and AWS-specific annotations

The example values also show the external dependency contract used by the chart:

- external Neo4j
- external Postgres for indexed content retrieval and search
- structured repository include rules rendered into `PCG_REPOSITORY_RULES_JSON`

This keeps the public example reusable while still documenting a realistic EKS path.

# Argo CD

Example Argo CD manifests live under:

- `deploy/argocd/base` — cloud-neutral base Application
- `deploy/argocd/overlays/aws` — AWS overlay with External Secrets and AWS-specific annotations

## What the examples show

The example values demonstrate the external dependency contract used by the chart:

- External Neo4j
- External Postgres for indexed content retrieval and search
- Structured repository include rules rendered into `PCG_REPOSITORY_RULES_JSON`

This keeps the examples reusable while documenting a realistic EKS deployment path.

## Minimal ApplicationSet example

If you manage multiple clusters or environments with ApplicationSets:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: platform-context-graph
  namespace: argocd
spec:
  generators:
    - list:
        elements:
          - cluster: staging
            url: https://staging-cluster-api:6443
          - cluster: production
            url: https://prod-cluster-api:6443
  template:
    metadata:
      name: 'pcg-{{cluster}}'
    spec:
      project: default
      source:
        repoURL: https://github.com/platformcontext/platform-context-graph.git
        targetRevision: main
        path: deploy/argocd/overlays/aws
      destination:
        server: '{{url}}'
        namespace: platform-context-graph
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

Adjust the `path` to match your overlay (base, aws, or a custom overlay).

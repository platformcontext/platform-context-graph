# ArgoCD Deployment

Deploying PCG manually means someone has to remember to update it. ArgoCD keeps the deployment in sync with the repo — auto-sync, self-heal, and environment overlays out of the box.

## Directory structure

PCG ships ArgoCD manifests under `deploy/argocd/`:

```
deploy/argocd/
├── base/
│   ├── application.yaml      # ArgoCD Application pointing at the Helm chart
│   ├── kustomization.yaml
│   └── values.yaml            # Cloud-neutral Helm values
└── overlays/
    └── aws/
        ├── application-patch.yaml   # Adds AWS overlay values
        ├── externalsecret-examples.yaml  # Neo4j + GitHub App credentials
        ├── kustomization.yaml
        └── values.yaml              # IRSA, ALB ingress, internal LB
```

## Base Application

The base `application.yaml` deploys PCG from the Helm chart with automated sync:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: platform-context-graph
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/platformcontext/platform-context-graph.git
    targetRevision: main
    path: deploy/helm/platform-context-graph
    helm:
      releaseName: platform-context-graph
      valueFiles:
        - deploy/argocd/base/values.yaml   # Helm values live alongside the manifests
  destination:
    server: https://kubernetes.default.svc
    namespace: platform-context-graph
  syncPolicy:
    automated:
      prune: true       # Remove resources deleted from git
      selfHeal: true    # Revert manual drift automatically
```

The base values configure Neo4j, Postgres (content store), repository sync via GitHub App, and observability hooks. See `deploy/argocd/base/values.yaml` for the full set.

## AWS overlay

The AWS overlay adds EKS-specific configuration on top of the base:

- **IRSA** — `eks.amazonaws.com/role-arn` annotation on the ServiceAccount
- **ALB Ingress** — internal Application Load Balancer with IP target type
- **External Secrets** — pulls Neo4j credentials and GitHub App keys from AWS Secrets Manager

Apply the overlay by pointing ArgoCD at `deploy/argocd/overlays/aws` instead of `base`.

## Multi-cluster with ApplicationSets

For staging + production or multi-cluster deployments, use an ApplicationSet:

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
        path: deploy/argocd/overlays/aws    # Swap for base or a custom overlay
      destination:
        server: '{{url}}'
        namespace: platform-context-graph
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

## Customization

- **New overlay** — copy `overlays/aws/` to `overlays/gcp/`, adjust values and patches
- **Different secret backend** — replace the ExternalSecret manifests with your provider (Vault, GCP Secret Manager)
- **Repository rules** — set `PCG_REPOSITORY_RULES_JSON` in values to control which repos get indexed
- **Observability** — enable OTEL export in values to send traces and metrics to your collector

## What PCG sees after deployment

Once deployed via ArgoCD, PCG can index its own ArgoCD Application. Run `trace_deployment_chain platform-context-graph` and PCG traces from the ArgoCD app through K8s resources to the Helm chart and source repo — a useful validation that the deployment topology is wired correctly.

## Next steps

- [Deployment Overview](overview.md) — other deployment options
- [Configuration Reference](../reference/configuration.md) — full environment variable and Helm value docs
- [How It Works](../concepts/how-it-works.md) — what happens after deployment when repos get indexed

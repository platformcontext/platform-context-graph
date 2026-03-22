# Minimal Manifests

For the smallest raw-manifest deployment example, use:

- `deploy/manifests/minimal`

This path is intentionally minimal:
- one namespace
- one config map
- one external Neo4j secret example
- one `StatefulSet`
- one `ClusterIP` service

It is useful when you want the least amount of Kubernetes machinery before moving to Helm or Argo CD.

Apply with:

```bash
kubectl apply -k deploy/manifests/minimal
```

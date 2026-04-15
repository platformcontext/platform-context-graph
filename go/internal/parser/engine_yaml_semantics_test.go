package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathYAMLArgoCDApplication(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "application.yaml")
	writeTestFile(
		t,
		filePath,
		`apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: iac-eks-addons
  namespace: argocd
spec:
  project: platform
  source:
    repoURL: https://github.com/myorg/iac-eks-argocd.git
    path: overlays/production/addons/cert-manager
    targetRevision: main
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: true
    syncOptions:
      - CreateNamespace=true
      - PruneLast=true
  destination:
    server: https://kubernetes.default.svc
    namespace: cert-manager
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertNamedBucketContains(t, got, "argocd_applications", "iac-eks-addons")
	assertBucketContainsFieldValue(t, got, "argocd_applications", "source_repo", "https://github.com/myorg/iac-eks-argocd.git")
	assertBucketContainsFieldValue(t, got, "argocd_applications", "source_path", "overlays/production/addons/cert-manager")
	assertBucketContainsFieldValue(t, got, "argocd_applications", "dest_server", "https://kubernetes.default.svc")
	assertBucketContainsFieldValue(t, got, "argocd_applications", "dest_namespace", "cert-manager")
	assertBucketContainsFieldValue(t, got, "argocd_applications", "sync_policy", "automated(prune=true,selfHeal=true,allowEmpty=true),syncOptions=CreateNamespace=true|PruneLast=true")
	assertBucketContainsFieldValue(t, got, "argocd_applications", "sync_policy_options", "CreateNamespace=true|PruneLast=true")
}

func TestDefaultEngineParsePathYAMLArgoCDApplicationSetNestedSources(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "applicationset.yaml")
	writeTestFile(
		t,
		filePath,
		`apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: api-node-search
  namespace: argocd
spec:
  generators:
    - merge:
        generators:
          - matrix:
              generators:
                - git:
                    repoURL: https://github.com/boatsgroup/helm-charts
                    files:
                      - path: argocd/api-node-search/overlays/*/config.yaml
                - list:
                    elements:
                      - cluster: prod
          - plugin:
              configMapRef:
                name: argocd-generator-plugin
  template:
    spec:
      project: "{{.argocd.project}}"
      sources:
        - repoURL: "{{.git.repoURL}}"
          path: argocd/api-node-search/overlays/{{.environment}}
      destination:
        namespace: "{{.helm.namespace}}"
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertNamedBucketContains(t, got, "argocd_applicationsets", "api-node-search")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "source_repos", "https://github.com/boatsgroup/helm-charts")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "source_paths", "argocd/api-node-search/overlays/*/config.yaml,argocd/api-node-search/overlays/{{.environment}}")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "source_roots", "argocd/api-node-search/")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "generators", "git,list,matrix,merge,plugin")
}

func TestDefaultEngineParsePathYAMLArgoCDApplicationSetPreservesGeneratorAndTemplateSources(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "applicationset-sources.yaml")
	writeTestFile(
		t,
		filePath,
		`apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: platform-appset
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://github.com/myorg/platform-config.git
        files:
          - path: argocd/platform/*/config.yaml
  template:
    spec:
      project: platform
      source:
        repoURL: https://github.com/myorg/platform-runtime.git
        path: deploy/overlays/prod
      destination:
        server: https://kubernetes.default.svc
        namespace: platform
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertNamedBucketContains(t, got, "argocd_applicationsets", "platform-appset")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "generator_source_repos", "https://github.com/myorg/platform-config.git")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "generator_source_paths", "argocd/platform/*/config.yaml")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "template_source_repos", "https://github.com/myorg/platform-runtime.git")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "template_source_paths", "deploy/overlays/prod")
	assertBucketContainsFieldValue(t, got, "argocd_applicationsets", "dest_server", "https://kubernetes.default.svc")
}

func TestDefaultEngineParsePathYAMLCrossplaneResources(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "crossplane.yaml")
	writeTestFile(
		t,
		filePath,
		`apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xiamroles.iam.aws.myorg.io
spec:
  group: iam.aws.myorg.io
  names:
    kind: XIAMRole
    plural: xiamroles
  claimNames:
    kind: IAMRole
    plural: iamroles
---
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: iam-role-composition
spec:
  compositeTypeRef:
    apiVersion: iam.aws.myorg.io/v1alpha1
    kind: XIAMRole
  resources:
    - name: iam-role
---
apiVersion: iam.aws.myorg.crossplane.io/v1alpha1
kind: IAMRole
metadata:
  name: my-service-role
  namespace: default
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertNamedBucketContains(t, got, "crossplane_xrds", "xiamroles.iam.aws.myorg.io")
	assertBucketContainsFieldValue(t, got, "crossplane_xrds", "claim_kind", "IAMRole")
	assertNamedBucketContains(t, got, "crossplane_compositions", "iam-role-composition")
	assertBucketContainsFieldValue(t, got, "crossplane_compositions", "composite_kind", "XIAMRole")
	assertNamedBucketContains(t, got, "crossplane_claims", "my-service-role")
	assertBucketContainsFieldValue(t, got, "crossplane_claims", "api_version", "iam.aws.myorg.crossplane.io/v1alpha1")
}

func TestDefaultEngineParsePathYAMLKustomizeAndHelm(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()

	kustomizePath := filepath.Join(repoRoot, "kustomization.yaml")
	writeTestFile(
		t,
		kustomizePath,
		`apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: production
resources:
  - ../base
  - ../app
patches:
  - path: patches/replicas.yaml
`,
	)

	chartPath := filepath.Join(repoRoot, "Chart.yaml")
	writeTestFile(
		t,
		chartPath,
		`name: my-api-chart
version: 0.1.0
appVersion: 1.0.0
dependencies:
  - name: redis
`,
	)

	valuesPath := filepath.Join(repoRoot, "values.yaml")
	writeTestFile(
		t,
		valuesPath,
		`replicaCount: 2
image:
  repository: ghcr.io/example/app
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	kustomizePayload, err := engine.ParsePath(repoRoot, kustomizePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", kustomizePath, err)
	}
	assertNamedBucketContains(t, kustomizePayload, "kustomize_overlays", "kustomization")
	assertBucketContainsFieldValue(t, kustomizePayload, "kustomize_overlays", "namespace", "production")
	kustomizeOverlays := kustomizePayload["kustomize_overlays"].([]map[string]any)
	if len(kustomizeOverlays) != 1 {
		t.Fatalf("kustomize_overlays = %#v, want one overlay", kustomizeOverlays)
	}
	bases, ok := kustomizeOverlays[0]["bases"].([]string)
	if !ok {
		t.Fatalf("kustomize_overlays[0].bases = %T, want []string", kustomizeOverlays[0]["bases"])
	}
	if len(bases) != 2 || bases[0] != "../app" || bases[1] != "../base" {
		t.Fatalf("kustomize_overlays[0].bases = %#v, want [../app ../base]", bases)
	}
	chartPayload, err := engine.ParsePath(repoRoot, chartPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", chartPath, err)
	}
	assertNamedBucketContains(t, chartPayload, "helm_charts", "my-api-chart")
	assertBucketContainsFieldValue(t, chartPayload, "helm_charts", "dependencies", "redis")

	valuesPayload, err := engine.ParsePath(repoRoot, valuesPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", valuesPath, err)
	}
	assertNamedBucketContains(t, valuesPayload, "helm_values", "values")
	assertBucketContainsFieldValue(t, valuesPayload, "helm_values", "top_level_keys", "image,replicaCount")
}

func TestDefaultEngineParsePathYAMLKustomizePatchTargets(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "kustomization.yaml")
	writeTestFile(
		t,
		filePath,
		`apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
patches:
  - target:
      kind: Deployment
      name: comprehensive-app
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 1
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	payload, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", filePath, err)
	}

	overlays := payload["kustomize_overlays"].([]map[string]any)
	if len(overlays) != 1 {
		t.Fatalf("kustomize_overlays = %#v, want one overlay", overlays)
	}
	patchTargets, ok := overlays[0]["patch_targets"].([]string)
	if !ok {
		t.Fatalf("kustomize_overlays[0].patch_targets = %T, want []string", overlays[0]["patch_targets"])
	}
	if len(patchTargets) != 1 || patchTargets[0] != "Deployment/comprehensive-app" {
		t.Fatalf("kustomize_overlays[0].patch_targets = %#v, want [Deployment/comprehensive-app]", patchTargets)
	}
}

func TestDefaultEngineParsePathYAMLCloudFormation(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "stack.yaml")
	writeTestFile(
		t,
		filePath,
		`AWSTemplateFormatVersion: "2010-09-09"
Parameters:
  Env:
    Type: String
    Default: dev
Resources:
  DataBucket:
    Type: AWS::S3::Bucket
  RolePolicy:
    Type: AWS::IAM::Policy
    DependsOn:
      - DataBucket
Outputs:
  BucketArn:
    Value: !GetAtt DataBucket.Arn
    Export:
      Name: Stack-BucketArn
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertNamedBucketContains(t, got, "cloudformation_resources", "DataBucket")
	assertBucketContainsFieldValue(t, got, "cloudformation_resources", "resource_type", "AWS::S3::Bucket")
	assertBucketContainsFieldValue(t, got, "cloudformation_resources", "depends_on", "DataBucket")
	assertNamedBucketContains(t, got, "cloudformation_parameters", "Env")
	assertNamedBucketContains(t, got, "cloudformation_outputs", "BucketArn")
	assertBucketContainsFieldValue(t, got, "cloudformation_outputs", "export_name", "Stack-BucketArn")
}

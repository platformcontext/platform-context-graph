package reducer

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/truth"
)

func TestNewDefaultRuntimeUsesDefaultDomainHandlers(t *testing.T) {
	t.Parallel()

	runtime, err := NewDefaultRuntime(DefaultHandlers{
		WorkloadIdentityWriter: &recordingWorkloadIdentityWriter{
			result: WorkloadIdentityWriteResult{
				CanonicalWrites: 1,
			},
		},
		CloudAssetResolutionWriter: &recordingCloudAssetResolutionWriter{
			result: CloudAssetResolutionWriteResult{
				CanonicalWrites: 1,
			},
		},
		PlatformMaterializationWriter: &recordingPlatformMaterializationWriter{
			result: PlatformMaterializationWriteResult{
				CanonicalWrites: 1,
			},
		},
		CodeCallEdgeWriter: &recordingCodeCallEdgeWriter{},
	})
	if err != nil {
		t.Fatalf("NewDefaultRuntime() error = %v, want nil", err)
	}

	workloadResult, err := runtime.Execute(context.Background(), Intent{
		IntentID:        "intent-1",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainWorkloadIdentity,
		Cause:           "shared identity follow-up required",
		EntityKeys:      []string{"workload:platform-context-graph"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("runtime.Execute(workload) error = %v, want nil", err)
	}
	if got, want := workloadResult.Status, ResultStatusSucceeded; got != want {
		t.Fatalf("runtime.Execute(workload).Status = %q, want %q", got, want)
	}

	cloudAssetResult, err := runtime.Execute(context.Background(), Intent{
		IntentID:        "intent-7",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainCloudAssetResolution,
		Cause:           "shared cloud asset follow-up required",
		EntityKeys:      []string{"aws:s3:bucket:logs-prod"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("runtime.Execute(cloud_asset) error = %v, want nil", err)
	}
	if got, want := cloudAssetResult.Status, ResultStatusSucceeded; got != want {
		t.Fatalf("runtime.Execute(cloud_asset).Status = %q, want %q", got, want)
	}

	deploymentResult, err := runtime.Execute(context.Background(), Intent{
		IntentID:        "intent-pm-1",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainDeploymentMapping,
		Cause:           "platform binding discovered",
		EntityKeys:      []string{"platform:kubernetes:aws:prod-cluster"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("runtime.Execute(deployment_mapping) error = %v, want nil", err)
	}
	if got, want := deploymentResult.Status, ResultStatusSucceeded; got != want {
		t.Fatalf("runtime.Execute(deployment_mapping).Status = %q, want %q", got, want)
	}

	_, err = runtime.Execute(context.Background(), Intent{
		IntentID:        "intent-2",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainGovernance,
		Cause:           "shared governance follow-up required",
		EntityKeys:      []string{"policy:default"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err == nil {
		t.Fatal("runtime.Execute(governance) error = nil, want non-nil")
	}
	if got, want := err.Error(), `domain "governance" is not registered`; got != want {
		t.Fatalf("runtime.Execute(governance) error = %q, want %q", got, want)
	}
}

func TestDefaultDomainDefinitionsMatchImplementedRuntimeCatalog(t *testing.T) {
	t.Parallel()

	got := DefaultDomainDefinitions()
	if len(got) != 6 {
		t.Fatalf("len(DefaultDomainDefinitions()) = %d, want 6", len(got))
	}
	if got[0].Domain != DomainWorkloadIdentity {
		t.Fatalf("DefaultDomainDefinitions()[0].Domain = %q, want %q", got[0].Domain, DomainWorkloadIdentity)
	}
	if got[0].TruthContract.CanonicalKind != "workload_identity" {
		t.Fatalf("DefaultDomainDefinitions()[0].TruthContract.CanonicalKind = %q, want %q", got[0].TruthContract.CanonicalKind, "workload_identity")
	}
	if !got[0].TruthContract.Supports(truth.LayerSourceDeclaration) {
		t.Fatal("DefaultDomainDefinitions()[0].TruthContract.Supports(source_declaration) = false, want true")
	}
	if got[1].Domain != DomainCloudAssetResolution {
		t.Fatalf("DefaultDomainDefinitions()[1].Domain = %q, want %q", got[1].Domain, DomainCloudAssetResolution)
	}
	if got[1].TruthContract.CanonicalKind != "cloud_asset" {
		t.Fatalf("DefaultDomainDefinitions()[1].TruthContract.CanonicalKind = %q, want %q", got[1].TruthContract.CanonicalKind, "cloud_asset")
	}
	if !got[1].TruthContract.Supports(truth.LayerAppliedDeclaration) {
		t.Fatal("DefaultDomainDefinitions()[1].TruthContract.Supports(applied_declaration) = false, want true")
	}
	if !got[1].TruthContract.Supports(truth.LayerObservedResource) {
		t.Fatal("DefaultDomainDefinitions()[1].TruthContract.Supports(observed_resource) = false, want true")
	}
	if got[3].Domain != DomainCodeCallMaterialization {
		t.Fatalf("DefaultDomainDefinitions()[3].Domain = %q, want %q", got[3].Domain, DomainCodeCallMaterialization)
	}
	if got[3].TruthContract.CanonicalKind != "code_call_materialization" {
		t.Fatalf("DefaultDomainDefinitions()[3].TruthContract.CanonicalKind = %q, want %q", got[3].TruthContract.CanonicalKind, "code_call_materialization")
	}
	if !got[3].TruthContract.Supports(truth.LayerSourceDeclaration) {
		t.Fatal("DefaultDomainDefinitions()[3].TruthContract.Supports(source_declaration) = false, want true")
	}
	if got[4].Domain != DomainWorkloadMaterialization {
		t.Fatalf("DefaultDomainDefinitions()[4].Domain = %q, want %q", got[4].Domain, DomainWorkloadMaterialization)
	}
	if got[5].Domain != DomainSemanticEntityMaterialization {
		t.Fatalf("DefaultDomainDefinitions()[5].Domain = %q, want %q", got[5].Domain, DomainSemanticEntityMaterialization)
	}
	if got[5].TruthContract.CanonicalKind != "semantic_entity_materialization" {
		t.Fatalf("DefaultDomainDefinitions()[5].TruthContract.CanonicalKind = %q, want %q", got[5].TruthContract.CanonicalKind, "semantic_entity_materialization")
	}
}

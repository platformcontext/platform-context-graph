package reducer

import (
	"context"
	"sort"
	"strings"
	"time"
)

// RepoRunIntentLister lists pending intents scoped to a specific repository,
// source run, and projection domain.
type RepoRunIntentLister interface {
	ListPendingRepoRunIntents(ctx context.Context, repositoryID, sourceRunID, domain string, limit int) ([]SharedProjectionIntentRow, error)
}

// PendingGenerationCounter counts pending intents for a specific repository,
// source run, generation, and projection domain.
type PendingGenerationCounter interface {
	CountPendingGenerationIntents(ctx context.Context, repositoryID, sourceRunID, generationID, domain string) (int, error)
}

// InlineFollowupConfig holds parameters for running inline shared projection
// draining after a reducer execution completes.
type InlineFollowupConfig struct {
	RepositoryID         string
	SourceRunID          string
	AcceptedGenerationID string
	AuthoritativeDomains []string
	PartitionCount       int
	LeaseOwner           string
	LeaseTTL             time.Duration
	BatchLimit           int
	EvidenceSource       string
}

func (c InlineFollowupConfig) partitionCount() int {
	if c.PartitionCount <= 0 {
		return defaultPartitionCount
	}
	return c.PartitionCount
}

func (c InlineFollowupConfig) leaseOwner() string {
	if c.LeaseOwner == "" {
		return "inline-shared-followup"
	}
	return c.LeaseOwner
}

func (c InlineFollowupConfig) leaseTTL() time.Duration {
	if c.LeaseTTL <= 0 {
		return defaultLeaseTTL
	}
	return c.LeaseTTL
}

func (c InlineFollowupConfig) batchLimit() int {
	if c.BatchLimit <= 0 {
		return defaultBatchLimit
	}
	return c.BatchLimit
}

func (c InlineFollowupConfig) evidenceSource() string {
	if c.EvidenceSource == "" {
		return defaultEvidenceSource
	}
	return c.EvidenceSource
}

// RunInlineSharedFollowup drains authoritative shared projection domains inline
// for one repository generation. It processes each domain by listing pending
// intents, computing affected partitions, and calling ProcessPartitionOnce per
// partition until all intents are drained or progress stalls.
//
// Returns the list of domains that could not be fully drained. An empty/nil
// return means all domains were successfully processed.
func RunInlineSharedFollowup(
	ctx context.Context,
	cfg InlineFollowupConfig,
	lister RepoRunIntentLister,
	counter PendingGenerationCounter,
	leaseManager PartitionLeaseManager,
	reader SharedIntentReader,
	edgeWriter SharedProjectionEdgeWriter,
) []string {
	domains := deduplicateDomains(cfg.AuthoritativeDomains)
	if len(domains) == 0 || strings.TrimSpace(cfg.AcceptedGenerationID) == "" {
		return nil
	}

	acceptedGen := func(repositoryID, sourceRunID string) (string, bool) {
		if repositoryID == cfg.RepositoryID && sourceRunID == cfg.SourceRunID {
			return cfg.AcceptedGenerationID, true
		}
		return "", false
	}

	partitionCount := cfg.partitionCount()
	var remaining []string

	for _, domain := range domains {
		if ctx.Err() != nil {
			remaining = append(remaining, domain)
			continue
		}

		if !drainDomain(ctx, cfg, domain, partitionCount, acceptedGen, lister, counter, leaseManager, reader, edgeWriter) {
			remaining = append(remaining, domain)
		}
	}

	return remaining
}

// drainDomain attempts to fully drain one projection domain. Returns true if
// all intents were processed, false if draining stalled or failed.
func drainDomain(
	ctx context.Context,
	cfg InlineFollowupConfig,
	domain string,
	partitionCount int,
	acceptedGen AcceptedGenerationLookup,
	lister RepoRunIntentLister,
	counter PendingGenerationCounter,
	leaseManager PartitionLeaseManager,
	reader SharedIntentReader,
	edgeWriter SharedProjectionEdgeWriter,
) bool {
	var previousRemaining *int

	for {
		if ctx.Err() != nil {
			return false
		}

		partitionIDs, err := pendingPartitionIDs(
			ctx, lister,
			cfg.RepositoryID, cfg.SourceRunID, domain,
			partitionCount,
		)
		if err != nil {
			return false
		}
		if len(partitionIDs) == 0 {
			return true
		}

		now := time.Now().UTC()
		for _, partitionID := range partitionIDs {
			ProcessPartitionOnce(
				ctx, now,
				PartitionProcessorConfig{
					Domain:         domain,
					PartitionID:    partitionID,
					PartitionCount: partitionCount,
					LeaseOwner:     cfg.leaseOwner(),
					LeaseTTL:       cfg.leaseTTL(),
					BatchLimit:     cfg.batchLimit(),
					EvidenceSource: cfg.evidenceSource(),
				},
				leaseManager,
				reader,
				edgeWriter,
				acceptedGen,
			)
		}

		count, err := counter.CountPendingGenerationIntents(
			ctx, cfg.RepositoryID, cfg.SourceRunID,
			cfg.AcceptedGenerationID, domain,
		)
		if err != nil {
			return false
		}
		if count <= 0 {
			return true
		}
		if previousRemaining != nil && count >= *previousRemaining {
			return false
		}
		previousRemaining = &count
	}
}

// pendingPartitionIDs lists pending intents for a repo/run/domain and returns
// the sorted unique partition IDs.
func pendingPartitionIDs(
	ctx context.Context,
	lister RepoRunIntentLister,
	repositoryID, sourceRunID, domain string,
	partitionCount int,
) ([]int, error) {
	intents, err := lister.ListPendingRepoRunIntents(ctx, repositoryID, sourceRunID, domain, 10000)
	if err != nil {
		return nil, err
	}
	if len(intents) == 0 {
		return nil, nil
	}

	seen := make(map[int]bool)
	for _, intent := range intents {
		p, err := PartitionForKey(intent.PartitionKey, partitionCount)
		if err != nil {
			continue
		}
		seen[p] = true
	}

	ids := make([]int, 0, len(seen))
	for id := range seen {
		ids = append(ids, id)
	}
	sort.Ints(ids)
	return ids, nil
}

// deduplicateDomains returns sorted unique non-empty domain strings.
func deduplicateDomains(domains []string) []string {
	seen := make(map[string]bool, len(domains))
	var result []string
	for _, d := range domains {
		d = strings.TrimSpace(d)
		if d != "" && !seen[d] {
			seen[d] = true
			result = append(result, d)
		}
	}
	sort.Strings(result)
	return result
}

package query

import (
	"context"
	"sync"
	"testing"
	"time"
)

func TestSearchConsumerEvidenceAnyRepoStartsBoundedSearchesConcurrently(t *testing.T) {
	t.Parallel()

	store := &blockingConsumerSearchContentStore{
		started: make(chan string, 3),
		release: make(chan struct{}),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	done := make(chan error, 1)
	go func() {
		_, err := searchConsumerEvidenceAnyRepo(
			ctx,
			store,
			"repo-sample-service-api",
			"sample-service-api",
			[]string{"sample-service.dev.example.test", "sample-service.qa.example.test"},
			25,
		)
		done <- err
	}()

	seen := map[string]struct{}{}
	for len(seen) < 3 {
		select {
		case term := <-store.started:
			seen[term] = struct{}{}
		case <-time.After(300 * time.Millisecond):
			t.Fatalf("started searches = %#v, want service-name and hostname searches to start before the first one completes", seen)
		}
	}
	close(store.release)

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("searchConsumerEvidenceAnyRepo() error = %v, want nil", err)
		}
	case <-time.After(time.Second):
		t.Fatal("searchConsumerEvidenceAnyRepo() did not complete after releasing blocked searches")
	}
}

type blockingConsumerSearchContentStore struct {
	fakePortContentStore
	started chan string
	release chan struct{}
	mu      sync.Mutex
	calls   []string
}

func (s *blockingConsumerSearchContentStore) SearchFileContentAnyRepo(ctx context.Context, pattern string, _ int) ([]FileContent, error) {
	return s.blockedSearch(ctx, pattern)
}

func (s *blockingConsumerSearchContentStore) SearchFileContentAnyRepoExactCase(ctx context.Context, pattern string, _ int) ([]FileContent, error) {
	return s.blockedSearch(ctx, pattern)
}

func (s *blockingConsumerSearchContentStore) blockedSearch(ctx context.Context, pattern string) ([]FileContent, error) {
	s.mu.Lock()
	s.calls = append(s.calls, pattern)
	s.mu.Unlock()
	select {
	case s.started <- pattern:
	case <-ctx.Done():
		return nil, ctx.Err()
	}
	select {
	case <-s.release:
		return nil, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

type patternConsumerSearchContentStore struct {
	fakePortContentStore
	fileRows  map[string][]FileContent
	exactRows map[string][]FileContent
}

func (s patternConsumerSearchContentStore) SearchFileContentAnyRepo(_ context.Context, pattern string, _ int) ([]FileContent, error) {
	return append([]FileContent(nil), s.fileRows[pattern]...), nil
}

func (s patternConsumerSearchContentStore) SearchFileContentAnyRepoExactCase(_ context.Context, pattern string, _ int) ([]FileContent, error) {
	return append([]FileContent(nil), s.exactRows[pattern]...), nil
}

package postgres

import (
	"context"
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
)

const upsertContentFileQuery = `
INSERT INTO content_files (
    repo_id, relative_path, commit_sha, content, content_hash,
    line_count, language, artifact_type, template_dialect,
    iac_relevant, indexed_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
)
ON CONFLICT (repo_id, relative_path) DO UPDATE
SET commit_sha = EXCLUDED.commit_sha,
    content = EXCLUDED.content,
    content_hash = EXCLUDED.content_hash,
    line_count = EXCLUDED.line_count,
    language = EXCLUDED.language,
    artifact_type = EXCLUDED.artifact_type,
    template_dialect = EXCLUDED.template_dialect,
    iac_relevant = EXCLUDED.iac_relevant,
    indexed_at = EXCLUDED.indexed_at
`

const deleteContentFileQuery = `
DELETE FROM content_files
WHERE repo_id = $1
  AND relative_path = $2
`

const deleteContentEntityQuery = `
DELETE FROM content_entities
WHERE repo_id = $1
  AND relative_path = $2
`

// ContentWriter persists repo-local content rows into the canonical content store.
//
// It only writes file rows because content.Record does not yet carry the entity
// identity and span data required to synthesize content_entities safely.
type ContentWriter struct {
	db  ExecQueryer
	Now func() time.Time
}

// NewContentWriter constructs a Postgres-backed canonical content writer.
func NewContentWriter(db ExecQueryer) ContentWriter {
	return ContentWriter{db: db}
}

// Write persists canonical file rows and removes tombstoned rows.
func (w ContentWriter) Write(ctx context.Context, materialization content.Materialization) (content.Result, error) {
	if w.db == nil {
		return content.Result{}, fmt.Errorf("content writer database is required")
	}

	cloned := materialization.Clone()
	if strings.TrimSpace(cloned.RepoID) == "" {
		return content.Result{}, fmt.Errorf("content materialization repo_id is required")
	}

	indexedAt := w.now()
	result := content.Result{
		ScopeID:      cloned.ScopeID,
		GenerationID: cloned.GenerationID,
		RecordCount:  len(cloned.Records),
	}

	for _, record := range cloned.Records {
		if strings.TrimSpace(record.Path) == "" {
			return content.Result{}, fmt.Errorf("content record path is required")
		}

		if record.Deleted {
			if _, err := w.db.ExecContext(ctx, deleteContentEntityQuery, cloned.RepoID, record.Path); err != nil {
				return content.Result{}, fmt.Errorf("delete content_entities for %q: %w", record.Path, err)
			}
			if _, err := w.db.ExecContext(ctx, deleteContentFileQuery, cloned.RepoID, record.Path); err != nil {
				return content.Result{}, fmt.Errorf("delete content_files for %q: %w", record.Path, err)
			}
			result.DeletedCount++
			continue
		}

		contentHash, err := fileContentHash(record)
		if err != nil {
			return content.Result{}, fmt.Errorf("derive content hash for %q: %w", record.Path, err)
		}

		commitSHA, err := optionalMetadataText(record.Metadata, "commit_sha")
		if err != nil {
			return content.Result{}, fmt.Errorf("commit_sha metadata for %q: %w", record.Path, err)
		}
		language, err := optionalMetadataText(record.Metadata, "language")
		if err != nil {
			return content.Result{}, fmt.Errorf("language metadata for %q: %w", record.Path, err)
		}
		artifactType, err := optionalMetadataText(record.Metadata, "artifact_type")
		if err != nil {
			return content.Result{}, fmt.Errorf("artifact_type metadata for %q: %w", record.Path, err)
		}
		templateDialect, err := optionalMetadataText(record.Metadata, "template_dialect")
		if err != nil {
			return content.Result{}, fmt.Errorf("template_dialect metadata for %q: %w", record.Path, err)
		}
		iacRelevant, err := optionalMetadataBool(record.Metadata, "iac_relevant")
		if err != nil {
			return content.Result{}, fmt.Errorf("iac_relevant metadata for %q: %w", record.Path, err)
		}

		if _, err := w.db.ExecContext(
			ctx,
			upsertContentFileQuery,
			cloned.RepoID,
			record.Path,
			commitSHA,
			record.Body,
			contentHash,
			lineCount(record.Body),
			language,
			artifactType,
			templateDialect,
			iacRelevant,
			indexedAt,
		); err != nil {
			return content.Result{}, fmt.Errorf("upsert content_files for %q: %w", record.Path, err)
		}
	}

	return result, nil
}

func (w ContentWriter) now() time.Time {
	if w.Now != nil {
		return w.Now().UTC()
	}
	return time.Now().UTC()
}

func fileContentHash(record content.Record) (string, error) {
	if strings.TrimSpace(record.Digest) != "" {
		return record.Digest, nil
	}

	sum := sha1.Sum([]byte(record.Body))
	return hex.EncodeToString(sum[:]), nil
}

func lineCount(contentText string) int {
	if contentText == "" {
		return 0
	}

	count := strings.Count(contentText, "\n")
	if strings.HasSuffix(contentText, "\n") {
		return count
	}

	return count + 1
}

func optionalMetadataText(metadata map[string]string, key string) (any, error) {
	if len(metadata) == 0 {
		return nil, nil
	}

	value, ok := metadata[key]
	if !ok {
		return nil, nil
	}

	text := strings.TrimSpace(value)
	if text == "" {
		return nil, nil
	}

	return text, nil
}

func optionalMetadataBool(metadata map[string]string, key string) (any, error) {
	if len(metadata) == 0 {
		return nil, nil
	}

	value, ok := metadata[key]
	if !ok {
		return nil, nil
	}

	text := strings.TrimSpace(value)
	if text == "" {
		return nil, nil
	}

	parsed, err := strconv.ParseBool(text)
	if err != nil {
		return nil, fmt.Errorf("parse %s %q as bool: %w", key, value, err)
	}

	return parsed, nil
}

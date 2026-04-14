package query

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

// ContentReader reads file and entity content from the Postgres content store.
type ContentReader struct {
	db     *sql.DB
	tracer trace.Tracer
}

// NewContentReader constructs a Postgres-backed content store reader.
func NewContentReader(db *sql.DB) *ContentReader {
	return &ContentReader{
		db:     db,
		tracer: otel.Tracer("platform-context-graph/go/internal/query"),
	}
}

// FileContent is one file from the content store.
type FileContent struct {
	RepoID       string `json:"repo_id"`
	RelativePath string `json:"relative_path"`
	CommitSHA    string `json:"commit_sha,omitempty"`
	Content      string `json:"content"`
	ContentHash  string `json:"content_hash"`
	LineCount    int    `json:"line_count"`
	Language     string `json:"language,omitempty"`
}

// EntityContent is one parsed entity from the content store.
type EntityContent struct {
	EntityID     string         `json:"entity_id"`
	RepoID       string         `json:"repo_id"`
	RelativePath string         `json:"relative_path"`
	EntityType   string         `json:"entity_type"`
	EntityName   string         `json:"entity_name"`
	StartLine    int            `json:"start_line"`
	EndLine      int            `json:"end_line"`
	Language     string         `json:"language,omitempty"`
	SourceCache  string         `json:"source_cache,omitempty"`
	Metadata     map[string]any `json:"metadata,omitempty"`
}

// GetFileContent returns one file by repo_id and relative_path.
func (cr *ContentReader) GetFileContent(ctx context.Context, repoID, relativePath string) (*FileContent, error) {
	ctx, span := cr.tracer.Start(ctx, "postgres.query",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "get_file_content"),
			attribute.String("db.sql.table", "content_files"),
		),
	)
	defer span.End()

	row := cr.db.QueryRowContext(ctx, `
		SELECT repo_id, relative_path, coalesce(commit_sha, ''),
		       content, content_hash, line_count, coalesce(language, '')
		FROM content_files
		WHERE repo_id = $1 AND relative_path = $2
	`, repoID, relativePath)

	var f FileContent
	err := row.Scan(&f.RepoID, &f.RelativePath, &f.CommitSHA,
		&f.Content, &f.ContentHash, &f.LineCount, &f.Language)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("get file content: %w", err)
	}
	return &f, nil
}

// GetFileLines returns a line range from one file.
func (cr *ContentReader) GetFileLines(ctx context.Context, repoID, relativePath string, startLine, endLine int) (*FileContent, error) {
	ctx, span := cr.tracer.Start(ctx, "postgres.query",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "get_file_lines"),
			attribute.String("db.sql.table", "content_files"),
		),
	)
	defer span.End()

	fc, err := cr.GetFileContent(ctx, repoID, relativePath)
	if err != nil || fc == nil {
		if err != nil {
			span.RecordError(err)
		}
		return fc, err
	}

	lines := strings.Split(fc.Content, "\n")
	if startLine < 1 {
		startLine = 1
	}
	if endLine < 1 || endLine > len(lines) {
		endLine = len(lines)
	}
	if startLine > len(lines) {
		fc.Content = ""
		fc.LineCount = 0
		return fc, nil
	}

	selected := lines[startLine-1 : endLine]
	fc.Content = strings.Join(selected, "\n")
	fc.LineCount = len(selected)
	return fc, nil
}

// GetEntityContent returns one entity by entity_id.
func (cr *ContentReader) GetEntityContent(ctx context.Context, entityID string) (*EntityContent, error) {
	ctx, span := cr.tracer.Start(ctx, "postgres.query",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "get_entity_content"),
			attribute.String("db.sql.table", "content_entities"),
		),
	)
	defer span.End()

	row := cr.db.QueryRowContext(ctx, `
		SELECT entity_id, repo_id, relative_path, entity_type, entity_name,
		       start_line, end_line, coalesce(language, ''), coalesce(source_cache, ''),
		       metadata
		FROM content_entities
		WHERE entity_id = $1
	`, entityID)

	var e EntityContent
	var rawMetadata []byte
	err := row.Scan(&e.EntityID, &e.RepoID, &e.RelativePath, &e.EntityType,
		&e.EntityName, &e.StartLine, &e.EndLine, &e.Language, &e.SourceCache, &rawMetadata)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("get entity content: %w", err)
	}
	e.Metadata, err = decodeEntityMetadata(rawMetadata)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("get entity content: %w", err)
	}
	return &e, nil
}

// SearchFileContent searches file content using trigram matching.
func (cr *ContentReader) SearchFileContent(ctx context.Context, repoID, pattern string, limit int) ([]FileContent, error) {
	ctx, span := cr.tracer.Start(ctx, "postgres.query",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "search_file_content"),
			attribute.String("db.sql.table", "content_files"),
		),
	)
	defer span.End()

	if limit <= 0 {
		limit = 50
	}

	query := `
		SELECT repo_id, relative_path, coalesce(commit_sha, ''),
		       '', content_hash, line_count, coalesce(language, '')
		FROM content_files
		WHERE repo_id = $1 AND content ILIKE '%' || $2 || '%'
		ORDER BY relative_path
		LIMIT $3
	`
	rows, err := cr.db.QueryContext(ctx, query, repoID, pattern, limit)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("search file content: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var results []FileContent
	for rows.Next() {
		var f FileContent
		if err := rows.Scan(&f.RepoID, &f.RelativePath, &f.CommitSHA,
			&f.Content, &f.ContentHash, &f.LineCount, &f.Language); err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("scan file search result: %w", err)
		}
		results = append(results, f)
	}
	if err := rows.Err(); err != nil {
		span.RecordError(err)
		return results, err
	}
	return results, nil
}

// SearchEntityContent searches entity source cache using trigram matching.
func (cr *ContentReader) SearchEntityContent(ctx context.Context, repoID, pattern string, limit int) ([]EntityContent, error) {
	ctx, span := cr.tracer.Start(ctx, "postgres.query",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "search_entity_content"),
			attribute.String("db.sql.table", "content_entities"),
		),
	)
	defer span.End()

	if limit <= 0 {
		limit = 50
	}

	query := `
		SELECT entity_id, repo_id, relative_path, entity_type, entity_name,
		       start_line, end_line, coalesce(language, ''), coalesce(source_cache, ''),
		       metadata
		FROM content_entities
		WHERE repo_id = $1 AND source_cache ILIKE '%' || $2 || '%'
		ORDER BY relative_path, start_line
		LIMIT $3
	`
	rows, err := cr.db.QueryContext(ctx, query, repoID, pattern, limit)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("search entity content: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var results []EntityContent
	for rows.Next() {
		var e EntityContent
		var rawMetadata []byte
		if err := rows.Scan(&e.EntityID, &e.RepoID, &e.RelativePath, &e.EntityType,
			&e.EntityName, &e.StartLine, &e.EndLine, &e.Language, &e.SourceCache, &rawMetadata); err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("scan entity search result: %w", err)
		}
		e.Metadata, err = decodeEntityMetadata(rawMetadata)
		if err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("scan entity search result: %w", err)
		}
		results = append(results, e)
	}
	if err := rows.Err(); err != nil {
		span.RecordError(err)
		return results, err
	}
	return results, nil
}

// ListRepoFiles returns all indexed files for one repository.
func (cr *ContentReader) ListRepoFiles(ctx context.Context, repoID string, limit int) ([]FileContent, error) {
	ctx, span := cr.tracer.Start(ctx, "postgres.query",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "list_repo_files"),
			attribute.String("db.sql.table", "content_files"),
		),
	)
	defer span.End()

	if limit <= 0 {
		limit = 500
	}

	rows, err := cr.db.QueryContext(ctx, `
		SELECT repo_id, relative_path, coalesce(commit_sha, ''),
		       '', content_hash, line_count, coalesce(language, '')
		FROM content_files
		WHERE repo_id = $1
		ORDER BY relative_path
		LIMIT $2
	`, repoID, limit)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("list repo files: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var results []FileContent
	for rows.Next() {
		var f FileContent
		if err := rows.Scan(&f.RepoID, &f.RelativePath, &f.CommitSHA,
			&f.Content, &f.ContentHash, &f.LineCount, &f.Language); err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("scan repo file: %w", err)
		}
		results = append(results, f)
	}
	if err := rows.Err(); err != nil {
		span.RecordError(err)
		return results, err
	}
	return results, nil
}

// ListRepoEntities returns all indexed entities for one repository.
func (cr *ContentReader) ListRepoEntities(ctx context.Context, repoID string, limit int) ([]EntityContent, error) {
	ctx, span := cr.tracer.Start(ctx, "postgres.query",
		trace.WithAttributes(
			attribute.String("db.system", "postgresql"),
			attribute.String("db.operation", "list_repo_entities"),
			attribute.String("db.sql.table", "content_entities"),
		),
	)
	defer span.End()

	if limit <= 0 {
		limit = 500
	}

	rows, err := cr.db.QueryContext(ctx, `
		SELECT entity_id, repo_id, relative_path, entity_type, entity_name,
		       start_line, end_line, coalesce(language, ''), coalesce(source_cache, ''),
		       metadata
		FROM content_entities
		WHERE repo_id = $1
		ORDER BY relative_path, start_line
		LIMIT $2
	`, repoID, limit)
	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("list repo entities: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var results []EntityContent
	for rows.Next() {
		var e EntityContent
		var rawMetadata []byte
		if err := rows.Scan(&e.EntityID, &e.RepoID, &e.RelativePath, &e.EntityType,
			&e.EntityName, &e.StartLine, &e.EndLine, &e.Language, &e.SourceCache, &rawMetadata); err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("scan repo entity: %w", err)
		}
		e.Metadata, err = decodeEntityMetadata(rawMetadata)
		if err != nil {
			span.RecordError(err)
			return nil, fmt.Errorf("scan repo entity: %w", err)
		}
		results = append(results, e)
	}
	if err := rows.Err(); err != nil {
		span.RecordError(err)
		return results, err
	}
	return results, nil
}

func decodeEntityMetadata(raw []byte) (map[string]any, error) {
	if len(raw) == 0 {
		return nil, nil
	}

	var metadata map[string]any
	if err := json.Unmarshal(raw, &metadata); err != nil {
		return nil, fmt.Errorf("decode entity metadata: %w", err)
	}
	if len(metadata) == 0 {
		return nil, nil
	}
	return metadata, nil
}

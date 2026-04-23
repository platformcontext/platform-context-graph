package query

import (
	"context"
	"database/sql"
	"fmt"
)

// ListRepositories returns repository catalog entries from the relational data plane.
func (cr *ContentReader) ListRepositories(ctx context.Context) ([]RepositoryCatalogEntry, error) {
	if cr == nil || cr.db == nil {
		return nil, nil
	}

	rows, err := cr.db.QueryContext(ctx, `
		SELECT scope_id AS id,
		       coalesce(payload->>'name', payload->>'repo_name', payload->>'repo_slug', scope_id) AS name,
		       coalesce(payload->>'path', '') AS path,
		       coalesce(payload->>'local_path', payload->>'path', '') AS local_path,
		       coalesce(payload->>'remote_url', '') AS remote_url,
		       coalesce(payload->>'repo_slug', '') AS repo_slug,
		       CASE WHEN coalesce(payload->>'remote_url', '') <> '' THEN true ELSE false END AS has_remote
		FROM ingestion_scopes
		WHERE scope_kind = 'repository'
		ORDER BY name, id
	`)
	if err != nil {
		return nil, fmt.Errorf("list repositories: %w", err)
	}
	defer func() { _ = rows.Close() }()

	repositories := make([]RepositoryCatalogEntry, 0)
	for rows.Next() {
		var repo RepositoryCatalogEntry
		if err := rows.Scan(
			&repo.ID,
			&repo.Name,
			&repo.Path,
			&repo.LocalPath,
			&repo.RemoteURL,
			&repo.RepoSlug,
			&repo.HasRemote,
		); err != nil {
			return nil, fmt.Errorf("scan repository catalog row: %w", err)
		}
		repositories = append(repositories, repo)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate repository catalog rows: %w", err)
	}
	return repositories, nil
}

// ResolveRepository resolves one repository selector from the relational catalog.
func (cr *ContentReader) ResolveRepository(ctx context.Context, selector string) (*RepositoryCatalogEntry, error) {
	if cr == nil || cr.db == nil {
		return nil, nil
	}

	row := cr.db.QueryRowContext(ctx, `
		SELECT scope_id AS id,
		       coalesce(payload->>'name', payload->>'repo_name', payload->>'repo_slug', scope_id) AS name,
		       coalesce(payload->>'path', '') AS path,
		       coalesce(payload->>'local_path', payload->>'path', '') AS local_path,
		       coalesce(payload->>'remote_url', '') AS remote_url,
		       coalesce(payload->>'repo_slug', '') AS repo_slug,
		       CASE WHEN coalesce(payload->>'remote_url', '') <> '' THEN true ELSE false END AS has_remote
		FROM ingestion_scopes
		WHERE scope_kind = 'repository'
		  AND (
			scope_id = $1 OR
			payload->>'name' = $1 OR
			payload->>'repo_name' = $1 OR
			payload->>'repo_slug' = $1 OR
			payload->>'path' = $1 OR
			payload->>'local_path' = $1
		  )
		ORDER BY scope_id
		LIMIT 1
	`, selector)

	var repo RepositoryCatalogEntry
	if err := row.Scan(
		&repo.ID,
		&repo.Name,
		&repo.Path,
		&repo.LocalPath,
		&repo.RemoteURL,
		&repo.RepoSlug,
		&repo.HasRemote,
	); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("resolve repository catalog row: %w", err)
	}
	return &repo, nil
}

# Query

The query package owns HTTP read surfaces, OpenAPI assembly, response
contracts, and graph/content read models.

The public OpenAPI contract is built in Go from `openapi*.go` fragments and is
served at `/api/v0/openapi.json`. Keep handler behavior, OpenAPI fragments, and
`docs/docs/reference/http-api.md` in agreement when changing public routes or
response shapes.

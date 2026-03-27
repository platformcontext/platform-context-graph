# OSS UI API Usage

## Rule

The OSS UI uses existing OSS APIs directly. It must not introduce enterprise
headers, enterprise route namespaces, or enterprise-only access concepts.

## Primary API Surfaces

### Search And Resolution

- `POST /api/v0/entities/resolve`
- `POST /api/v0/code/search`
- `POST /api/v0/content/files/search`
- `POST /api/v0/content/entities/search`

### Detail And Context Views

- `GET /api/v0/entities/{id}/context`
- `GET /api/v0/workloads/{id}/context`
- `GET /api/v0/services/{id}/context`
- `GET /api/v0/repositories`
- `GET /api/v0/repositories/{id}/context`
- `GET /api/v0/repositories/{id}/stats`

### Analysis Views

- `POST /api/v0/traces/resource-to-code`
- `POST /api/v0/paths/explain`
- `POST /api/v0/impact/change-surface`
- `POST /api/v0/environments/compare`
- `POST /api/v0/infra/resources/search`
- `POST /api/v0/infra/relationships`
- `GET /api/v0/ecosystem/overview`

### Runtime And Status

- `GET /api/v0/health`
- `GET /api/v0/index-status`
- `GET /api/v0/ingesters`
- `GET /api/v0/ingesters/{ingester}`
- `GET /api/v0/index-runs/{run_id}/coverage`

## Client-Side Rules

- treat OSS API responses as canonical
- do not add workspace or tenant routing headers
- do not reinterpret IDs into enterprise-scoped objects
- keep local saved query presets client-side unless an OSS-safe persistence
  mechanism is explicitly added later

## Error Handling Expectations

- surface API problem details clearly
- distinguish "no data yet" from "server unavailable"
- keep empty-state copy engine-focused and single-user-focused

## Future Compatibility

The enterprise UI can later proxy many of the same query routes, but the OSS UI
must remain valid and useful without any enterprise backend in front of it.

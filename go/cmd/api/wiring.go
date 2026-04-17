package main

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"net/http"
	"strings"

	_ "github.com/jackc/pgx/v5/stdlib"
	neo4jdriver "github.com/neo4j/neo4j-go-driver/v5/neo4j"

	"github.com/platformcontext/platform-context-graph/go/internal/query"
	"github.com/platformcontext/platform-context-graph/go/internal/recovery"
	internalruntime "github.com/platformcontext/platform-context-graph/go/internal/runtime"
	"github.com/platformcontext/platform-context-graph/go/internal/status"
	pgstatus "github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func wireAPI(
	ctx context.Context,
	getenv func(string) string,
	logger *slog.Logger,
	prometheusHandler http.Handler,
) (http.Handler, func(), error) {
	apiKey, err := internalruntime.ResolveAPIKey(getenv)
	if err != nil {
		return nil, nil, fmt.Errorf("resolve api key: %w", err)
	}

	// Open Neo4j
	neo4jURI := envOrDefault(getenv, "NEO4J_URI", "bolt://localhost:7687")
	neo4jUser := envOrDefault(getenv, "NEO4J_USERNAME", "neo4j")
	neo4jPass := envOrDefault(getenv, "NEO4J_PASSWORD", "")
	neo4jDB := envOrDefault(getenv, "DEFAULT_DATABASE", "neo4j")

	driver, err := neo4jdriver.NewDriverWithContext(
		neo4jURI,
		neo4jdriver.BasicAuth(neo4jUser, neo4jPass, ""),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("open neo4j: %w", err)
	}

	if err := driver.VerifyConnectivity(ctx); err != nil {
		_ = driver.Close(ctx)
		return nil, nil, fmt.Errorf("verify neo4j: %w", err)
	}
	if logger != nil {
		logger.Info("neo4j connected", telemetry.EventAttr("runtime.neo4j.connected"), slog.String("neo4j_uri", neo4jURI))
	}

	// Open Postgres using pgx driver
	pgDSN := envOrDefault(getenv, "PCG_POSTGRES_DSN",
		envOrDefault(getenv, "PCG_CONTENT_STORE_DSN", ""))
	if pgDSN == "" {
		_ = driver.Close(ctx)
		return nil, nil, fmt.Errorf("PCG_POSTGRES_DSN or PCG_CONTENT_STORE_DSN is required")
	}

	db, err := sql.Open("pgx", pgDSN)
	if err != nil {
		_ = driver.Close(ctx)
		return nil, nil, fmt.Errorf("open postgres: %w", err)
	}
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		_ = driver.Close(ctx)
		return nil, nil, fmt.Errorf("ping postgres: %w", err)
	}
	if logger != nil {
		logger.Info("postgres connected", telemetry.EventAttr("runtime.postgres.connected"))
	}

	// Build query layer
	neo4jReader := query.NewNeo4jReader(driver, neo4jDB)
	contentReader := query.NewContentReader(db)
	statusReader := pgstatus.NewStatusStore(pgstatus.SQLQueryer{DB: db})
	router, err := newRouter(db, neo4jReader, contentReader)
	if err != nil {
		_ = db.Close()
		_ = driver.Close(ctx)
		return nil, nil, fmt.Errorf("new router: %w", err)
	}

	apiMux := http.NewServeMux()
	router.Mount(apiMux)

	mux, err := mountRuntimeSurface(apiMux, "platform-context-graph-api", statusReader, prometheusHandler)
	if err != nil {
		_ = db.Close()
		_ = driver.Close(ctx)
		return nil, nil, fmt.Errorf("mount runtime surface: %w", err)
	}

	// Wrap with auth middleware
	authedMux := query.AuthMiddleware(apiKey, mux)

	cleanup := func() {
		_ = db.Close()
		_ = driver.Close(context.Background())
	}

	return authedMux, cleanup, nil
}

func envOrDefault(getenv func(string) string, key, fallback string) string {
	v := strings.TrimSpace(getenv(key))
	if v == "" {
		return fallback
	}
	return v
}

func newRouter(db *sql.DB, neo4jReader *query.Neo4jReader, contentReader *query.ContentReader) (*query.APIRouter, error) {
	router := &query.APIRouter{
		Repositories: &query.RepositoryHandler{
			Neo4j:   neo4jReader,
			Content: contentReader,
		},
		Entities: &query.EntityHandler{
			Neo4j:   neo4jReader,
			Content: contentReader,
		},
		Code: &query.CodeHandler{
			Neo4j:   neo4jReader,
			Content: contentReader,
		},
		Content: &query.ContentHandler{
			Content: contentReader,
		},
		Infra: &query.InfraHandler{
			Neo4j: neo4jReader,
		},
		Impact: &query.ImpactHandler{
			Neo4j:   neo4jReader,
			Content: contentReader,
		},
		Status: &query.StatusHandler{
			Neo4j:        neo4jReader,
			DB:           db,
			StatusReader: pgstatus.NewStatusStore(pgstatus.SQLQueryer{DB: db}),
		},
		Compare: &query.CompareHandler{
			Neo4j: neo4jReader,
		},
		Admin: &query.AdminHandler{
			Store: query.NewPostgresAdminStore(db),
		},
	}
	if db == nil {
		return router, nil
	}

	recoveryHandler, err := recovery.NewHandler(pgstatus.NewRecoveryStore(pgstatus.SQLDB{DB: db}))
	if err != nil {
		return nil, fmt.Errorf("new recovery handler: %w", err)
	}
	reindexer, err := internalruntime.NewStatusRequestHandler(pgstatus.NewStatusRequestStore(pgstatus.SQLDB{DB: db}))
	if err != nil {
		return nil, fmt.Errorf("new status request handler: %w", err)
	}
	router.Admin.Recovery = recoveryHandler
	router.Admin.Reindexer = reindexer
	return router, nil
}

func mountRuntimeSurface(
	apiHandler http.Handler,
	serviceName string,
	reader status.Reader,
	prometheusHandler http.Handler,
) (http.Handler, error) {
	adminMux, err := internalruntime.NewStatusAdminMux(
		serviceName,
		reader,
		apiHandler,
		internalruntime.WithPrometheusHandler(prometheusHandler),
	)
	if err != nil {
		return nil, err
	}
	return adminMux, nil
}

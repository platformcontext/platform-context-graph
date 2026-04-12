package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"strings"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const defaultFormat = "text"

func main() {
	if err := run(context.Background(), os.Args[1:], os.Stdout, os.Stderr, os.Getenv); err != nil {
		log.Fatal(err)
	}
}

func run(
	parent context.Context,
	args []string,
	stdout io.Writer,
	stderr io.Writer,
	getenv func(string) string,
) error {
	flags := flag.NewFlagSet("admin-status", flag.ContinueOnError)
	flags.SetOutput(stderr)

	format := flags.String("format", defaultFormat, "output format: text or json")
	if err := flags.Parse(args); err != nil {
		return err
	}

	dsn := factStoreDSN(getenv)
	if dsn == "" {
		return fmt.Errorf("set PCG_FACT_STORE_DSN, PCG_CONTENT_STORE_DSN, or PCG_POSTGRES_DSN")
	}

	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return fmt.Errorf("open postgres connection: %w", err)
	}
	defer db.Close()

	ctx, cancel := context.WithTimeout(parent, 10*time.Second)
	defer cancel()

	if err := db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping postgres: %w", err)
	}

	store := postgres.NewStatusStore(postgres.SQLQueryer{DB: db})
	raw, err := store.ReadRawSnapshot(ctx, time.Now().UTC())
	if err != nil {
		return err
	}

	report := statuspkg.BuildReport(raw, statuspkg.DefaultOptions())
	switch strings.ToLower(strings.TrimSpace(*format)) {
	case "text", "":
		_, err = fmt.Fprintln(stdout, statuspkg.RenderText(report))
		return err
	case "json":
		payload, err := statuspkg.RenderJSON(report)
		if err != nil {
			return fmt.Errorf("render json: %w", err)
		}
		_, err = fmt.Fprintln(stdout, string(payload))
		return err
	default:
		return fmt.Errorf("unsupported format %q", *format)
	}
}

func factStoreDSN(getenv func(string) string) string {
	for _, key := range []string{
		"PCG_FACT_STORE_DSN",
		"PCG_CONTENT_STORE_DSN",
		"PCG_POSTGRES_DSN",
	} {
		if value := strings.TrimSpace(getenv(key)); value != "" {
			return value
		}
	}

	return ""
}

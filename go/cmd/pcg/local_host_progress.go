package main

import (
	"context"
	"database/sql"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	statuspkg "github.com/platformcontext/platform-context-graph/go/internal/status"
	pgstorage "github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const defaultLocalHostProgressPollInterval = 3 * time.Second

type localHostProgressStop func() error

var (
	localHostOpenProgressDB = func(dsn string) (*sql.DB, error) {
		return sql.Open("pgx", dsn)
	}
	localHostLoadProgressReport = func(ctx context.Context, reader statuspkg.Reader, asOf time.Time) (statuspkg.Report, error) {
		return statuspkg.LoadReport(ctx, reader, asOf, statuspkg.DefaultOptions())
	}
	localHostProgressWriter       io.Writer = os.Stderr
	localHostProgressNow                    = func() time.Time { return time.Now().UTC() }
	localHostProgressPollInterval           = defaultLocalHostProgressPollInterval
)

func startLocalHostProgressReporter(
	ctx context.Context,
	workspaceRoot string,
	dsn string,
	runtimeConfig localHostRuntimeConfig,
) (localHostProgressStop, error) {
	db, err := localHostOpenProgressDB(dsn)
	if err != nil {
		return nil, fmt.Errorf("open local progress status connection: %w", err)
	}
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ping local progress status connection: %w", err)
	}

	reader := pgstorage.NewStatusStore(pgstorage.SQLQueryer{DB: db})
	reporterCtx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})

	go func() {
		defer close(done)

		ticker := time.NewTicker(localHostProgressPollInterval)
		defer ticker.Stop()

		lastRendered := ""
		for {
			report, err := localHostLoadProgressReport(reporterCtx, reader, localHostProgressNow())
			if err == nil {
				rendered := renderLocalHostProgressSnapshot(workspaceRoot, runtimeConfig, report)
				if rendered != lastRendered {
					_, _ = io.WriteString(localHostProgressWriter, rendered)
					lastRendered = rendered
				}
			}

			select {
			case <-reporterCtx.Done():
				return
			case <-ticker.C:
			}
		}
	}()

	return func() error {
		cancel()
		<-done
		return db.Close()
	}, nil
}

func renderLocalHostProgressSnapshot(
	workspaceRoot string,
	runtimeConfig localHostRuntimeConfig,
	report statuspkg.Report,
) string {
	var builder strings.Builder
	builder.WriteString("\n")
	builder.WriteString("Local progress ")
	builder.WriteString(report.AsOf.Format(time.RFC3339))
	builder.WriteString("\n")
	fmt.Fprintf(
		&builder,
		"  Owner: running | profile=%s | backend=%s | workspace=%s\n",
		runtimeConfig.Profile,
		localHostProgressBackendLabel(runtimeConfig),
		workspaceRoot,
	)
	fmt.Fprintf(&builder, "  Health: %s\n", report.Health.State)

	for _, row := range report.FlowSummaries {
		fmt.Fprintf(
			&builder,
			"  %s: progress=%s | backlog=%s\n",
			localHostProgressLaneLabel(row.Lane),
			row.Progress,
			row.Backlog,
		)
	}

	fmt.Fprintf(
		&builder,
		"  Queue: pending=%d in_flight=%d retrying=%d dead_letter=%d failed=%d oldest=%s\n",
		report.Queue.Pending,
		report.Queue.InFlight,
		report.Queue.Retrying,
		report.Queue.DeadLetter,
		report.Queue.Failed,
		localHostProgressAge(report.Queue.OldestOutstandingAge),
	)
	return builder.String()
}

func localHostProgressBackendLabel(runtimeConfig localHostRuntimeConfig) string {
	if runtimeConfig.GraphBackend == "" {
		return "none"
	}
	return string(runtimeConfig.GraphBackend)
}

func localHostProgressAge(age time.Duration) string {
	if age <= 0 {
		return "0s"
	}
	if age < time.Second {
		return age.String()
	}
	return age.Truncate(time.Second).String()
}

func localHostProgressLaneLabel(lane string) string {
	if lane == "" {
		return "Lane"
	}
	return strings.ToUpper(lane[:1]) + lane[1:]
}

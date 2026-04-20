package main

import (
	"log/slog"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
	"go.opentelemetry.io/otel/trace"
)

const defaultCollectorPollInterval = time.Second

func buildCollectorService(
	database postgres.SQLDB,
	getenv func(string) string,
	tracer trace.Tracer,
	instruments *telemetry.Instruments,
	logger *slog.Logger,
) (collector.Service, error) {
	config, err := collector.LoadRepoSyncConfig("collector-git", getenv)
	if err != nil {
		return collector.Service{}, err
	}

	return collector.Service{
		Source: &collector.GitSource{
			Component: "collector-git",
			Selector:  collector.NativeRepositorySelector{Config: config},
			Snapshotter: collector.NativeRepositorySnapshotter{
				SCIP:         collector.LoadSnapshotSCIPConfig(getenv),
				ParseWorkers: config.ParseWorkers,
				Tracer:       tracer,
				Instruments:  instruments,
				Logger:       logger,
			},
			SnapshotWorkers:        config.SnapshotWorkers,
			LargeRepoThreshold:     config.LargeRepoThreshold,
			LargeRepoMaxConcurrent: config.LargeRepoMaxConcurrent,
			StreamBuffer:           config.StreamBuffer,
			Tracer:                 tracer,
			Instruments:            instruments,
			Logger:                 logger,
		},
		Committer:    postgres.NewIngestionStore(database),
		PollInterval: defaultCollectorPollInterval,
		Tracer:       tracer,
		Instruments:  instruments,
		Logger:       logger,
	}, nil
}

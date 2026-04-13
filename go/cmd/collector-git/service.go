package main

import (
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

const defaultCollectorPollInterval = time.Second

func buildCollectorService(
	database postgres.SQLDB,
	getenv func(string) string,
	getwd func() (string, error),
	environ func() []string,
) (collector.Service, error) {
	config, err := collector.LoadRepoSyncConfig("collector-git", getenv)
	if err != nil {
		return collector.Service{}, err
	}

	return collector.Service{
		Source: &collector.GitSource{
			Component:   "collector-git",
			Selector:    collector.NativeRepositorySelector{Config: config},
			Snapshotter: collector.NativeRepositorySnapshotter{},
		},
		Committer:    postgres.NewIngestionStore(database),
		PollInterval: defaultCollectorPollInterval,
	}, nil
}

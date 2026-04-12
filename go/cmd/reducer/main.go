package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
)

func main() {
	if err := run(context.Background()); err != nil {
		log.Fatal(err)
	}
}

func run(parent context.Context) error {
	service, err := app.New("reducer")
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return service.Run(ctx)
}

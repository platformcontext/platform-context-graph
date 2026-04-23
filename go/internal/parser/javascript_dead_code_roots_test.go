package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathJavaScriptEmitsDeadCodeRootKinds(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	nextPath := filepath.Join(repoRoot, "app", "api", "health", "route.ts")
	expressPath := filepath.Join(repoRoot, "server", "routes.ts")
	writeTestFile(
		t,
		nextPath,
		`export async function GET() {
  return Response.json({ ok: true });
}

async function helper() {
  return Response.json({ ok: true });
}
`,
	)
	writeTestFile(
		t,
		expressPath,
		`import express from "express";

const router = express.Router();

function login(req, res) {
  return res.send("ok");
}

const createVideo = (req, res) => res.send("ok");

router.get("/auth/login", login);
router.post("/", createVideo);
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	nextPayload, err := engine.ParsePath(repoRoot, nextPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(next) error = %v, want nil", err)
	}
	expressPayload, err := engine.ParsePath(repoRoot, expressPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(express) error = %v, want nil", err)
	}

	assertParserStringSliceFieldValue(
		t,
		assertFunctionByName(t, nextPayload, "GET"),
		"dead_code_root_kinds",
		[]string{"javascript.nextjs_route_export"},
	)
	helperItem := assertFunctionByName(t, nextPayload, "helper")
	if _, ok := helperItem["dead_code_root_kinds"]; ok {
		t.Fatalf("dead_code_root_kinds = %#v, want absent for non-exported route helper", helperItem["dead_code_root_kinds"])
	}
	assertParserStringSliceFieldValue(
		t,
		assertFunctionByName(t, expressPayload, "login"),
		"dead_code_root_kinds",
		[]string{"javascript.express_route_registration"},
	)
	assertParserStringSliceFieldValue(
		t,
		assertFunctionByName(t, expressPayload, "createVideo"),
		"dead_code_root_kinds",
		[]string{"javascript.express_route_registration"},
	)
}

package parser

import (
	"path/filepath"
	"reflect"
	"testing"
)

func TestDefaultEngineParsePathPythonFastAPISemantics(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "fastapi_app.py")
	writeTestFile(
		t,
		filePath,
		`from fastapi import APIRouter, FastAPI, Request

app: FastAPI = FastAPI()
router: APIRouter = APIRouter(prefix="/api")

@app.get("/health")
def health():
    return {"ok": True}

@router.post("/predict")
async def predict(_request: Request):
    return {"score": 1.0}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertFrameworksEqual(t, got, "fastapi")
	assertNestedStringSliceEqual(t, got, "fastapi", "route_methods", []string{"GET", "POST"})
	assertNestedStringSliceEqual(t, got, "fastapi", "route_paths", []string{"/health", "/api/predict"})
	assertNestedStringSliceEqual(t, got, "fastapi", "server_symbols", []string{"app", "router"})
}

func TestDefaultEngineParsePathPythonFlaskSemantics(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "flask_app.py")
	writeTestFile(
		t,
		filePath,
		`from lib.factory import create_app

app = create_app(__name__)

@app.route("/health")
def health():
    return "ok"

@app.route("/proxy", methods=["GET", "POST"])
def proxy():
    return "proxied"
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertFrameworksEqual(t, got, "flask")
	assertNestedStringSliceEqual(t, got, "flask", "route_methods", []string{"GET", "POST"})
	assertNestedStringSliceEqual(t, got, "flask", "route_paths", []string{"/health", "/proxy"})
	assertNestedStringSliceEqual(t, got, "flask", "server_symbols", []string{"app"})
}

func TestDefaultEngineParsePathPythonORMMappings(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	sqlAlchemyPath := filepath.Join(repoRoot, "sqlalchemy_models.py")
	writeTestFile(
		t,
		sqlAlchemyPath,
		`from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
`,
	)

	djangoPath := filepath.Join(repoRoot, "django_models.py")
	writeTestFile(
		t,
		djangoPath,
		`from django.db import models

class AuditEvent(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "audit.events"
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	sqlAlchemyPayload, err := engine.ParsePath(repoRoot, sqlAlchemyPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", sqlAlchemyPath, err)
	}
	assertORMMappingsEqual(
		t,
		sqlAlchemyPayload,
		[]map[string]any{{
			"class_name":        "User",
			"class_line_number": 6,
			"table_name":        "users",
			"framework":         "sqlalchemy",
			"line_number":       7,
		}},
	)

	djangoPayload, err := engine.ParsePath(repoRoot, djangoPath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath(%q) error = %v, want nil", djangoPath, err)
	}
	assertORMMappingsEqual(
		t,
		djangoPayload,
		[]map[string]any{{
			"class_name":        "AuditEvent",
			"class_line_number": 3,
			"table_name":        "audit.events",
			"framework":         "django",
			"line_number":       7,
		}},
	)
}

func TestDefaultEngineParsePathPythonUnknownRouteDecoratorRemainsUnclassified(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "custom_router.py")
	writeTestFile(
		t,
		filePath,
		`class Router:
    def route(self, _path):
        def decorator(func):
            return func
        return decorator

router = Router()

@router.route("/health")
def health():
    return "ok"
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertFrameworksEqual(t, got)
}

func assertORMMappingsEqual(t *testing.T, payload map[string]any, want []map[string]any) {
	t.Helper()

	got, ok := payload["orm_table_mappings"].([]map[string]any)
	if !ok {
		t.Fatalf("orm_table_mappings = %T, want []map[string]any", payload["orm_table_mappings"])
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("orm_table_mappings = %#v, want %#v", got, want)
	}
}

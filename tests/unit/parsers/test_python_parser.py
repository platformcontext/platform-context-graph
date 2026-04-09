"""Tests for the handwritten Python parser facade."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.python import (
    PythonTreeSitterParser,
    pre_scan_python,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


class TestPythonParser:
    """Test the Python parser logic."""

    @pytest.fixture(scope="class")
    def parser(self):
        """Build a parser instance backed by the real tree-sitter grammar."""
        # We need to construct a PythonTreeSitterParser
        # It takes a wrapper. Let's mock the wrapper or create a real one.
        # Real one:
        manager = get_tree_sitter_manager()

        # Create a mock wrapper that behaves like the one expected by PythonTreeSitterParser
        wrapper = MagicMock()
        wrapper.language_name = "python"
        wrapper.language = manager.get_language_safe("python")
        wrapper.parser = manager.create_parser("python")

        return PythonTreeSitterParser(wrapper)

    def test_parse_simple_function(self, parser, temp_test_dir):
        """Parse a simple python file and verify output."""
        code = "def hello():\n    print('world')"
        f = temp_test_dir / "test.py"
        f.write_text(code)

        # Act
        result = parser.parse(str(f))

        # Assert
        # We expect a list of nodes/edges or a structure containing them
        # This structure depends on the actual return type of .parse()
        # For now, I will assert keys exist.

        print(f"DEBUG: Parser result keys: {result.keys()}")

        assert "functions" in result
        funcs = result["functions"]
        assert len(funcs) == 1
        assert funcs[0]["name"] == "hello"

    def test_parse_class_with_method(self, parser, temp_test_dir):
        """Parse a class with a method."""
        code = """
class Greeter:
    def greet(self, name):
        return f"Hello {name}"
"""
        f = temp_test_dir / "classes.py"
        f.write_text(code)

        result = parser.parse(str(f))

        assert "classes" in result
        classes = result["classes"]
        assert len(classes) == 1
        assert classes[0]["name"] == "Greeter"

        # Check methods if they are nested or separate
        # Depending on implementation, methods might be in 'functions' with parent info
        # or inside 'classes'.
        # Let's assume they are captured.

    def test_parse_imports_calls_and_inheritance(self, parser, temp_test_dir):
        """Parse Python imports, function calls, and inheritance metadata."""
        code = """
import os
from pathlib import Path

class Animal:
    pass

class Dog(Animal):
    pass

def build_path(name):
    return os.path.join(str(Path(name)), "child")
"""
        f = temp_test_dir / "relations.py"
        f.write_text(code)

        result = parser.parse(str(f))

        assert len(result["imports"]) >= 2
        assert any(item["name"] == "join" for item in result["function_calls"])
        dog = next(item for item in result["classes"] if item["name"] == "Dog")
        assert "Animal" in dog["bases"]

    def test_parse_async_functions_do_not_emit_async_flag(self, parser, temp_test_dir):
        """Async function definitions are parsed as functions without async metadata."""
        code = """
async def fetch_remote():
    return "ok"
"""
        f = temp_test_dir / "async_fn.py"
        f.write_text(code)

        result = parser.parse(str(f))

        fetch_remote = next(
            item for item in result["functions"] if item["name"] == "fetch_remote"
        )
        assert "async" not in fetch_remote

    def test_pre_scan_python_keeps_public_import_surface(self, temp_test_dir) -> None:
        """Return a name-to-file map through the legacy module import path."""
        manager = get_tree_sitter_manager()
        wrapper = MagicMock()
        wrapper.language_name = "python"
        wrapper.language = manager.get_language_safe("python")
        wrapper.parser = manager.create_parser("python")

        source_file = temp_test_dir / "prescan_sample.py"
        source_file.write_text(
            "class Greeter:\n    pass\n\n\ndef greet(name):\n    return name\n",
            encoding="utf-8",
        )

        imports_map = pre_scan_python([source_file], wrapper)

        assert imports_map["Greeter"] == [str(source_file.resolve())]
        assert imports_map["greet"] == [str(source_file.resolve())]

    def test_parse_variables_and_omits_decorator_metadata(
        self, parser, temp_test_dir, monkeypatch
    ):
        """Parse variable assignments while documenting missing decorator metadata."""
        monkeypatch.setenv("PCG_VARIABLE_SCOPE", "all")
        code = """
MODULE_LEVEL = 3

def traced(func):
    return func

@traced
def greet(name):
    local_value = name.upper()
    return local_value
"""
        f = temp_test_dir / "decorated.py"
        f.write_text(code)

        result = parser.parse(str(f))

        variables = result["variables"]
        assert any(item["name"] == "MODULE_LEVEL" for item in variables)
        assert any(item["name"] == "local_value" for item in variables)

        functions = result["functions"]
        greet = next(item for item in functions if item["name"] == "greet")
        assert greet["decorators"] == []

    def test_parse_does_not_emit_type_annotation_bucket(self, parser, temp_test_dir):
        """Type annotations are not emitted as a dedicated parse bucket today."""
        code = """
def greet(name: str) -> str:
    return name
"""
        f = temp_test_dir / "annotations.py"
        f.write_text(code)

        result = parser.parse(str(f))

        assert "type_annotations" not in result

    def test_parse_fastapi_route_semantics(self, parser, temp_test_dir):
        """Expose FastAPI route semantics for decorator-based apps."""

        code = """
from fastapi import APIRouter, FastAPI, Request

app = FastAPI()
router = APIRouter(prefix="/api")

@app.get("/health")
def health():
    return {"ok": True}

@router.post("/predict")
async def predict(_request: Request):
    return {"score": 1.0}
"""
        f = temp_test_dir / "fastapi_app.py"
        f.write_text(code)

        result = parser.parse(str(f))

        semantics = result["framework_semantics"]

        assert semantics["frameworks"] == ["fastapi"]
        assert semantics["fastapi"]["route_methods"] == ["GET", "POST"]
        assert semantics["fastapi"]["route_paths"] == ["/health", "/api/predict"]
        assert semantics["fastapi"]["server_symbols"] == ["app", "router"]

    def test_parse_fastapi_route_semantics_with_annotated_assignments(
        self, parser, temp_test_dir
    ):
        """Handle annotated FastAPI app/router assignments as route owners."""

        code = """
from fastapi import APIRouter, FastAPI

app: FastAPI = FastAPI()
router: APIRouter = APIRouter(prefix="/v1")

@app.get("/health")
def health():
    return {"ok": True}

@router.post("/predict")
async def predict():
    return {"score": 1.0}
"""
        f = temp_test_dir / "fastapi_annotated.py"
        f.write_text(code)

        result = parser.parse(str(f))

        semantics = result["framework_semantics"]

        assert semantics["frameworks"] == ["fastapi"]
        assert semantics["fastapi"]["route_methods"] == ["GET", "POST"]
        assert semantics["fastapi"]["route_paths"] == ["/health", "/v1/predict"]
        assert semantics["fastapi"]["server_symbols"] == ["app", "router"]

    def test_parse_flask_route_semantics(self, parser, temp_test_dir):
        """Expose Flask route semantics for app.route decorators."""

        code = """
from flask import Flask

app = Flask(__name__)

@app.route("/health")
def health():
    return "ok"

@app.route("/proxy", methods=["GET", "POST"])
def proxy():
    return "proxied"
"""
        f = temp_test_dir / "flask_app.py"
        f.write_text(code)

        result = parser.parse(str(f))

        semantics = result["framework_semantics"]

        assert semantics["frameworks"] == ["flask"]
        assert semantics["flask"]["route_methods"] == ["GET", "POST"]
        assert semantics["flask"]["route_paths"] == ["/health", "/proxy"]
        assert semantics["flask"]["server_symbols"] == ["app"]

    def test_parse_flask_factory_route_semantics(self, parser, temp_test_dir):
        """Treat imported Flask app factories as bounded route owners."""

        code = """
from lib.factory import create_app

app = create_app(__name__)

@app.route("/health", methods=["GET"])
def health():
    return "ok"
"""
        f = temp_test_dir / "flask_factory_route.py"
        f.write_text(code)

        result = parser.parse(str(f))

        semantics = result["framework_semantics"]

        assert semantics["frameworks"] == ["flask"]
        assert semantics["flask"]["route_methods"] == ["GET"]
        assert semantics["flask"]["route_paths"] == ["/health"]
        assert semantics["flask"]["server_symbols"] == ["app"]

    def test_parse_flask_error_handlers_do_not_count_as_routes(
        self, parser, temp_test_dir
    ):
        """Ignore Flask error handlers when building route semantics."""

        code = """
from flask import Flask

app = Flask(__name__)

@app.errorhandler(404)
def not_found(_error):
    return "missing", 404
"""
        f = temp_test_dir / "flask_factory.py"
        f.write_text(code)

        result = parser.parse(str(f))

        semantics = result["framework_semantics"]

        assert semantics["frameworks"] == []
        assert "flask" not in semantics

    def test_parse_unknown_route_decorators_do_not_count_as_flask(
        self, parser, temp_test_dir
    ):
        """Avoid classifying arbitrary `.route()` decorators as Flask."""

        code = """
class Router:
    def route(self, _path):
        def decorator(func):
            return func
        return decorator

router = Router()

@router.route("/health")
def health():
    return "ok"
"""
        f = temp_test_dir / "custom_router.py"
        f.write_text(code)

        result = parser.parse(str(f))

        semantics = result["framework_semantics"]

        assert semantics["frameworks"] == []
        assert "flask" not in semantics

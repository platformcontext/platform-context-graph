"""Tests for the handwritten JavaScript parser facade and support module."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.javascript import (
    JavascriptTreeSitterParser,
)
from platform_context_graph.parsers.languages.javascript_support import (
    pre_scan_javascript,
)
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def javascript_parser() -> JavascriptTreeSitterParser:
    """Build a JavaScript parser when the grammar is available."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("javascript"):
        pytest.skip(
            "JavaScript tree-sitter grammar is not available in this environment"
        )

    wrapper = MagicMock()
    wrapper.language_name = "javascript"
    wrapper.language = manager.get_language_safe("javascript")
    wrapper.parser = manager.create_parser("javascript")
    return JavascriptTreeSitterParser(wrapper)


def test_parse_javascript_simple_declarations(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Parse a small JavaScript file and verify key declarations are captured."""
    source = """
import fs from "node:fs";

class Greeter {
  greet(name) {
    return name;
  }
}

const hello = function helloWorld(value) {
  return value;
};
"""
    source_file = temp_test_dir / "sample.js"
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    assert any(item["name"] == "Greeter" for item in result["classes"])
    assert any(item["name"] == "hello" for item in result["functions"])
    assert any(item["name"] == "node:fs" for item in result["imports"])


def test_pre_scan_javascript_keeps_public_import_surface(temp_test_dir) -> None:
    """Return a name-to-file map through the JavaScript support module."""
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("javascript"):
        pytest.skip(
            "JavaScript tree-sitter grammar is not available in this environment"
        )

    wrapper = MagicMock()
    wrapper.language_name = "javascript"
    wrapper.language = manager.get_language_safe("javascript")
    wrapper.parser = manager.create_parser("javascript")

    source_file = temp_test_dir / "prescan_sample.js"
    source_file.write_text(
        "class Greeter {}\nfunction hello() {}\nconst world = () => world;\n",
        encoding="utf-8",
    )

    imports_map = pre_scan_javascript([source_file], wrapper)

    assert imports_map["Greeter"] == [str(source_file.resolve())]
    assert imports_map["hello"] == [str(source_file.resolve())]


def test_parse_javascript_runtime_surface(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Parse the JavaScript constructs referenced by the capability spec."""
    source = """
import helper from "./helper.js";

/** Documented utility. */
const documented = function documented(value) {
  return helper(value);
};

const increment = (value) => helper(value + 1);
const version = "1.0.0";

class Counter {
  get count() {
    return version.length;
  }

  async load() {
    return helper(version);
  }
}
"""
    source_file = temp_test_dir / "runtime_surface.js"
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file, index_source=True)

    assert any(item["name"] == "documented" for item in result["functions"])
    assert any(item["name"] == "increment" for item in result["functions"])
    assert any(item["name"] == "Counter" for item in result["classes"])
    assert any(item["source"] == "./helper.js" for item in result["imports"])
    assert any(item["name"] == "helper" for item in result["function_calls"])
    assert any(item["name"] == "version" for item in result["variables"])
    assert all(item.get("docstring") is None for item in result["functions"])
    assert any(item.get("type") == "getter" for item in result["functions"])


def test_parse_javascript_minified_value_keeps_full_initializer(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Minified files should still parse fully before the persistence preview cap."""

    payload = "x" * 256
    source_file = temp_test_dir / "bundle.min.js"
    source_file.write_text(
        f'var BIG={{"payload":"{payload}"}};\n',
        encoding="utf-8",
    )

    result = javascript_parser.parse(source_file)

    variable = next(item for item in result["variables"] if item["name"] == "BIG")
    assert variable["value"] is not None
    assert payload in variable["value"]
    assert len(variable["value"]) > 200


def test_parse_javascript_client_component_semantics(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Expose React semantic facts for JSX client component modules."""

    source = """\
'use client';

import React, { useState } from 'react';
import { useToolbarOverflow } from './hooks/useToolbarOverflow';

export function ToolbarButton() {
  const [open, setOpen] = useState(false);
  useToolbarOverflow();
  return <button onClick={() => setOpen(!open)}>{String(open)}</button>;
}
"""
    source_file = temp_test_dir / "ToolbarButton.jsx"
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["react"]
    assert semantics["react"]["boundary"] == "client"
    assert semantics["react"]["component_exports"] == ["ToolbarButton"]
    assert semantics["react"]["hooks_used"] == ["useState", "useToolbarOverflow"]


def test_parse_javascript_hapi_route_module_semantics(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Expose Hapi route-array semantics for route definition modules."""

    source = """\
const userController = require('../controller/userController');

const userRoutes = [
  { method: 'GET', path: '/users', handler: userController.getUsers },
  { method: 'POST', path: '/users', handler: userController.createUser },
  { method: 'DELETE', path: '/users/{id}', handler: userController.deleteUser },
];

module.exports = userRoutes;
"""
    source_file = temp_test_dir / "routes" / "userRoutes.js"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["hapi"]
    assert semantics["hapi"]["route_methods"] == ["GET", "POST", "DELETE"]
    assert semantics["hapi"]["route_paths"] == [
        "/users",
        "/users/{id}",
    ]
    assert semantics["hapi"]["server_symbols"] == []


def test_parse_javascript_express_router_semantics(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Expose Express router semantics for router modules."""

    source = """\
const express = require('express');
const router = express.Router();
const video = require('./handlers/video');

router.get('/auth/login', video.login);
router.post('/', video.sendVideo);

module.exports = router;
"""
    source_file = temp_test_dir / "server" / "routes.js"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["express"]
    assert semantics["express"]["route_methods"] == ["GET", "POST"]
    assert semantics["express"]["route_paths"] == ["/auth/login", "/"]
    assert semantics["express"]["server_symbols"] == ["router"]


def test_parse_javascript_hapi_request_tests_do_not_count_as_route_modules(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Hapi request-injection tests should not be classified as route modules."""

    source = """\
const { expect } = require('@hapi/code');

async function exercise(server) {
  const response = await server.inject({
    method: 'GET',
    url: '/users/123',
  });
  expect(response.statusCode).to.equal(200);
}
"""
    source_file = temp_test_dir / "test" / "users.lab.js"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    assert "hapi" not in result["framework_semantics"]["frameworks"]


def test_parse_javascript_aws_provider_semantics(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Expose bounded AWS SDK semantics for JavaScript modules."""

    source = """\
const { S3Client, GetObjectCommand } = require('@aws-sdk/client-s3');

const client = new S3Client({ region: 'us-east-1' });
const command = new GetObjectCommand({ Bucket: 'demo', Key: 'boats.csv' });
"""
    source_file = temp_test_dir / "consumer-utils.js"
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["aws"]
    assert semantics["aws"]["services"] == ["s3"]
    assert semantics["aws"]["client_symbols"] == ["S3Client"]


def test_parse_javascript_gcp_provider_semantics(
    javascript_parser: JavascriptTreeSitterParser, temp_test_dir
) -> None:
    """Expose bounded GCP SDK semantics for JavaScript modules."""

    source = """\
const vision = require('@google-cloud/vision');

async function analyze() {
  const client = new vision.ImageAnnotatorClient();
  return client;
}
"""
    source_file = temp_test_dir / "ImageAnalysisService.js"
    source_file.write_text(source, encoding="utf-8")

    result = javascript_parser.parse(source_file)

    semantics = result["framework_semantics"]

    assert semantics["frameworks"] == ["gcp"]
    assert semantics["gcp"]["services"] == ["vision"]
    assert semantics["gcp"]["client_symbols"] == ["ImageAnnotatorClient"]

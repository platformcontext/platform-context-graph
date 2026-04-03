"""Tests for the targeted JSON config parser."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.tools.languages.json_config import (
    JSONConfigTreeSitterParser,
)


class TestJSONConfigParser:
    """Verify filename-targeted JSON extraction stays useful and low-noise."""

    def test_parse_package_json_dependencies_and_scripts(
        self, temp_test_dir: Path
    ) -> None:
        """package.json should emit dependency variables and script functions."""

        file_path = temp_test_dir / "package.json"
        file_path.write_text(
            json.dumps(
                {
                    "name": "payments-api",
                    "version": "1.0.0",
                    "scripts": {
                        "build": "tsc -p tsconfig.json",
                        "start": "node dist/index.js",
                    },
                    "dependencies": {"express": "^4.19.2"},
                    "devDependencies": {"typescript": "^5.6.0"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        deps = {item["name"]: item for item in result["variables"]}
        scripts = {item["name"]: item for item in result["functions"]}

        assert result["lang"] == "json"
        assert deps["express"]["value"] == "^4.19.2"
        assert deps["express"]["section"] == "dependencies"
        assert deps["typescript"]["section"] == "devDependencies"
        assert scripts["build"]["source"] == "tsc -p tsconfig.json"
        assert scripts["start"]["function_kind"] == "json_script"

    def test_parse_composer_json_require_sections(self, temp_test_dir: Path) -> None:
        """composer.json should emit require and require-dev dependencies."""

        file_path = temp_test_dir / "composer.json"
        file_path.write_text(
            json.dumps(
                {
                    "name": "acme/payments-api",
                    "require": {"php": "^8.3", "laravel/framework": "^11.0"},
                    "require-dev": {"phpunit/phpunit": "^11.0"},
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        deps = {item["name"]: item for item in result["variables"]}

        assert deps["php"]["section"] == "require"
        assert deps["laravel/framework"]["value"] == "^11.0"
        assert deps["phpunit/phpunit"]["section"] == "require-dev"
        assert result["functions"] == []

    def test_parse_tsconfig_references_and_paths(self, temp_test_dir: Path) -> None:
        """tsconfig.json should emit extends, reference, and path alias metadata."""

        file_path = temp_test_dir / "tsconfig.json"
        file_path.write_text(
            json.dumps(
                {
                    "extends": "./tsconfig.base.json",
                    "compilerOptions": {
                        "paths": {"@app/*": ["src/*", "generated/*"]},
                    },
                    "references": [{"path": "../shared"}, {"path": "../infra"}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        values = {item["name"]: item for item in result["variables"]}

        assert values["extends"]["value"] == "./tsconfig.base.json"
        assert values["reference:../shared"]["config_kind"] == "reference"
        assert values["reference:../infra"]["value"] == "../infra"
        assert values["path:@app/*"]["value"] == "src/*,generated/*"

    def test_skip_non_config_json(self, temp_test_dir: Path) -> None:
        """Generic JSON files should stay metadata-only instead of emitting nodes."""

        file_path = temp_test_dir / "data.json"
        file_path.write_text('{"service":"payments-api","port":8080}', encoding="utf-8")

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        assert result["functions"] == []
        assert result["variables"] == []
        assert result["json_metadata"]["top_level_keys"] == ["service", "port"]

    def test_parse_cloudformation_json_template(self, temp_test_dir: Path) -> None:
        """JSON CloudFormation templates should still produce CFN graph entities."""

        file_path = temp_test_dir / "stack.json"
        file_path.write_text(
            json.dumps(
                {
                    "AWSTemplateFormatVersion": "2010-09-09",
                    "Resources": {
                        "AppBucket": {"Type": "AWS::S3::Bucket"},
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        assert result["cloudformation_resources"][0]["name"] == "AppBucket"
        assert result["cloudformation_resources"][0]["lang"] == "json"

    def test_parse_empty_json_file_as_metadata_only(self, temp_test_dir: Path) -> None:
        """Empty JSON files should not fail indexing or emit noisy entities."""

        file_path = temp_test_dir / "empty.json"
        file_path.write_text("", encoding="utf-8")

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        assert result["functions"] == []
        assert result["variables"] == []
        assert result["json_metadata"]["top_level_keys"] == []

    def test_parse_helm_templated_json_with_leading_directives(
        self, temp_test_dir: Path
    ) -> None:
        """Helm-templated JSON should parse after stripping directive preamble."""

        file_path = temp_test_dir / "base.json"
        file_path.write_text(
            "\n".join(
                [
                    '{{- $env := required "env is required" .Values.env | trim -}}',
                    '{{- $accountId := required "accountId is required" .Values.accountId | trim -}}',
                    "{",
                    '  "api-node-boats": {',
                    '    "client": {',
                    '      "hostname": "api-node-boats.{{ $env }}.bgrp.io",',
                    '      "port": 3081',
                    "    }",
                    "  }",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        assert result["functions"] == []
        assert result["variables"] == []
        assert result["json_metadata"]["top_level_keys"] == ["api-node-boats"]

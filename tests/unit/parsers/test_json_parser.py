"""Tests for the targeted JSON config parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from platform_context_graph.parsers.languages.json_config import (
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

    @pytest.mark.parametrize("filename", ["tsconfig.json", "tsconfig.base.json"])
    def test_parse_tsconfig_jsonc_comments_and_trailing_commas(
        self, temp_test_dir: Path, filename: str
    ) -> None:
        """tsconfig*.json should tolerate JSONC comments and trailing commas."""

        file_path = temp_test_dir / filename
        file_path.write_text(
            "\n".join(
                [
                    "{",
                    "  // shared config",
                    '  "extends": "./tsconfig.shared.json",',
                    '  "compilerOptions": {',
                    '    "paths": {',
                    '      "@app/*": ["src/*", "generated/*",],',
                    "    },",
                    "  },",
                    '  "references": [{"path": "../shared"},],',
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        values = {item["name"]: item for item in result["variables"]}

        assert values["extends"]["value"] == "./tsconfig.shared.json"
        assert values["reference:../shared"]["config_kind"] == "reference"
        assert values["path:@app/*"]["value"] == "src/*,generated/*"

    def test_non_tsconfig_json_with_comments_stays_strict(
        self, temp_test_dir: Path
    ) -> None:
        """Generic JSON files should still reject JSONC-only syntax."""

        file_path = temp_test_dir / "data.json"
        file_path.write_text(
            "\n".join(
                ["{", "  // not allowed here", '  "service": "payments-api"', "}"]
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")

        with pytest.raises(json.JSONDecodeError):
            parser.parse(file_path)

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

    def test_parse_dbt_manifest_into_data_intelligence_payload(
        self, temp_test_dir: Path
    ) -> None:
        """dbt manifest JSON should emit analytics entities and lineage hints."""

        file_path = temp_test_dir / "manifest.json"
        file_path.write_text(
            json.dumps(
                {
                    "metadata": {
                        "adapter_type": "postgres",
                        "project_name": "jaffle_shop",
                    },
                    "nodes": {
                        "model.jaffle_shop.order_metrics": {
                            "unique_id": "model.jaffle_shop.order_metrics",
                            "resource_type": "model",
                            "name": "order_metrics",
                            "database": "analytics",
                            "schema": "public",
                            "alias": "order_metrics",
                            "path": "models/marts/order_metrics.sql",
                            "compiled_path": (
                                "target/compiled/jaffle_shop/"
                                "models/marts/order_metrics.sql"
                            ),
                            "relation_name": "analytics.public.order_metrics",
                            "config": {"materialized": "view"},
                            "depends_on": {
                                "nodes": [
                                    "source.jaffle_shop.raw.orders",
                                    "source.jaffle_shop.raw.customers",
                                ]
                            },
                            "compiled_code": (
                                "select o.id as order_id, "
                                "c.full_name as customer_name "
                                "from raw.public.orders o "
                                "join raw.public.customers c on c.id = o.customer_id"
                            ),
                            "columns": {
                                "order_id": {"name": "order_id"},
                                "customer_name": {"name": "customer_name"},
                            },
                        }
                    },
                    "sources": {
                        "source.jaffle_shop.raw.orders": {
                            "unique_id": "source.jaffle_shop.raw.orders",
                            "resource_type": "source",
                            "source_name": "raw",
                            "name": "orders",
                            "database": "raw",
                            "schema": "public",
                            "identifier": "orders",
                            "columns": {
                                "id": {"name": "id"},
                                "customer_id": {"name": "customer_id"},
                            },
                        },
                        "source.jaffle_shop.raw.customers": {
                            "unique_id": "source.jaffle_shop.raw.customers",
                            "resource_type": "source",
                            "source_name": "raw",
                            "name": "customers",
                            "database": "raw",
                            "schema": "public",
                            "identifier": "customers",
                            "columns": {
                                "id": {"name": "id"},
                                "full_name": {"name": "full_name"},
                            },
                        },
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        assert [item["name"] for item in result["analytics_models"]] == [
            "order_metrics"
        ]
        assert [item["name"] for item in result["data_assets"]] == [
            "analytics.public.order_metrics",
            "raw.public.customers",
            "raw.public.orders",
        ]
        assert any(
            item["type"] == "COMPILES_TO"
            and item["source_name"] == "order_metrics"
            and item["target_name"] == "analytics.public.order_metrics"
            for item in result["data_relationships"]
        )
        assert any(
            item["type"] == "COLUMN_DERIVES_FROM"
            and item["source_name"] == "analytics.public.order_metrics.customer_name"
            and item["target_name"] == "raw.public.customers.full_name"
            for item in result["data_relationships"]
        )
        assert result["data_intelligence_coverage"]["state"] == "complete"

    def test_parse_dbt_replay_manifest_filename_variant(
        self, temp_test_dir: Path
    ) -> None:
        """Replay fixtures named ``dbt_manifest.json`` should parse as dbt artifacts."""

        manifest_path = temp_test_dir / "dbt_manifest.json"
        source_path = (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "ecosystems"
            / "analytics_compiled_comprehensive"
            / "dbt_manifest.json"
        )
        manifest_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(manifest_path)

        assert [item["name"] for item in result["analytics_models"]] == [
            "order_metrics",
            "orders_expanded",
        ]
        assert result["data_intelligence_coverage"]["state"] == "partial"

    def test_parse_warehouse_replay_json_into_data_intelligence_payload(
        self, temp_test_dir: Path
    ) -> None:
        """Warehouse replay JSON should emit assets, queries, and observed edges."""

        fixture_path = (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "ecosystems"
            / "warehouse_replay_comprehensive"
            / "warehouse_replay.json"
        )
        file_path = temp_test_dir / "warehouse_replay.json"
        file_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        assert [item["name"] for item in result["query_executions"]] == [
            "daily_revenue_build",
            "revenue_dashboard_lookup",
        ]
        assert any(
            item["type"] == "RUNS_QUERY_AGAINST"
            and item["source_name"] == "daily_revenue_build"
            and item["target_name"] == "analytics.finance.revenue"
            for item in result["data_relationships"]
        )
        assert result["data_intelligence_coverage"]["state"] == "complete"

    def test_parse_bi_replay_json_into_data_intelligence_payload(
        self, temp_test_dir: Path
    ) -> None:
        """BI replay JSON should emit dashboards and downstream lineage hints."""

        fixture_path = (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "ecosystems"
            / "bi_replay_comprehensive"
            / "bi_replay.json"
        )
        file_path = temp_test_dir / "bi_replay.json"
        file_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

        parser = JSONConfigTreeSitterParser("json")
        result = parser.parse(file_path)

        assert [item["name"] for item in result["dashboard_assets"]] == [
            "Revenue Overview"
        ]
        assert any(
            item["type"] == "POWERS"
            and item["source_name"] == "analytics.finance.daily_revenue"
            and item["target_name"] == "Revenue Overview"
            for item in result["data_relationships"]
        )
        assert any(
            item["type"] == "POWERS"
            and item["source_name"] == "analytics.finance.daily_revenue.gross_amount"
            and item["target_name"] == "Revenue Overview"
            for item in result["data_relationships"]
        )
        assert result["data_intelligence_coverage"]["state"] == "complete"

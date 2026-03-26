"""Integration tests for targeted JSON config extraction."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


class TestJSONGraph:
    """Verify the JSON fixture repo produces the expected graph entities."""

    def test_package_json_dependencies_indexed(self, indexed_ecosystems) -> None:
        """package.json dependencies should become variable nodes."""

        driver = indexed_ecosystems.get_driver()
        with driver.session() as session:
            rows = session.run(
                "MATCH (v:Variable) "
                "WHERE v.path CONTAINS 'json_comprehensive/package.json' "
                "RETURN v.name as name, v.section as section, v.value as value"
            ).data()

        values = {row["name"]: row for row in rows}
        assert values["express"]["section"] == "dependencies"
        assert values["typescript"]["section"] == "devDependencies"

    def test_package_json_scripts_indexed(self, indexed_ecosystems) -> None:
        """package.json scripts should become function nodes."""

        driver = indexed_ecosystems.get_driver()
        with driver.session() as session:
            rows = session.run(
                "MATCH (f:Function) "
                "WHERE f.path CONTAINS 'json_comprehensive/package.json' "
                "RETURN f.name as name, f.source as source"
            ).data()

        values = {row["name"]: row["source"] for row in rows}
        assert values["build"] == "tsc -p tsconfig.json"
        assert values["start"] == "node dist/index.js"

    def test_composer_json_dependencies_indexed(self, indexed_ecosystems) -> None:
        """composer.json require sections should become variable nodes."""

        driver = indexed_ecosystems.get_driver()
        with driver.session() as session:
            rows = session.run(
                "MATCH (v:Variable) "
                "WHERE v.path CONTAINS 'json_comprehensive/composer.json' "
                "RETURN v.name as name, v.section as section"
            ).data()

        values = {row["name"]: row["section"] for row in rows}
        assert values["php"] == "require"
        assert values["phpunit/phpunit"] == "require-dev"

    def test_tsconfig_json_metadata_indexed(self, indexed_ecosystems) -> None:
        """tsconfig.json should emit targeted config variables for references and paths."""

        driver = indexed_ecosystems.get_driver()
        with driver.session() as session:
            rows = session.run(
                "MATCH (v:Variable) "
                "WHERE v.path CONTAINS 'json_comprehensive/tsconfig.json' "
                "RETURN v.name as name, v.config_kind as config_kind, v.value as value"
            ).data()

        values = {row["name"]: row for row in rows}
        assert values["extends"]["value"] == "./tsconfig.base.json"
        assert values["reference:../shared"]["config_kind"] == "reference"
        assert values["path:@app/*"]["config_kind"] == "path"

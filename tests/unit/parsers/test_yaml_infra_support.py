"""Tests for Jinja-tolerant YAML loading helpers."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.tools.languages import yaml_infra_support


def test_safe_load_all_recovers_from_jinja_loop_blocks(monkeypatch) -> None:
    """Jinja control lines should not drop otherwise parseable YAML."""

    warnings: list[str] = []
    monkeypatch.setattr(
        yaml_infra_support,
        "warning_logger",
        lambda message: warnings.append(message),
    )
    content = """\
asset_group:
  name: branchio_ingestion

glue_jobs:
  - name: branchio_ingestion_job
    job_name: "branchio-api-ingestion-{{ region }}"

  {%- set models = ['click', 'install'] -%}
  {%- for model in models %}
  - name: branchio_datacontract_{{ model }}s
    job_name: "data-contract-handler-gluejob"
  {%- endfor %}
"""

    documents = yaml_infra_support.safe_load_all(content)

    assert warnings == []
    assert len(documents) == 1
    assert documents[0]["asset_group"]["name"] == "branchio_ingestion"
    assert [item["name"] for item in documents[0]["glue_jobs"]] == [
        "branchio_ingestion_job",
        "branchio_datacontract_{{ model }}s",
    ]


def test_load_yaml_dict_recovers_from_multiline_jinja_set_block(
    tmp_path: Path, monkeypatch
) -> None:
    """Multiline Jinja set blocks should not force a hard YAML parse failure."""

    warnings: list[str] = []
    monkeypatch.setattr(
        yaml_infra_support,
        "warning_logger",
        lambda message: warnings.append(message),
    )
    file_path = tmp_path / "ga4_dq_checks.yaml"
    file_path.write_text(
        """\
asset_group:
  name: ga4_data_quality

{% set portals = [
  'boats.com',
  'yachtworld'
] %}

dq_checks:
  - name: ga4_missing_parameters
    portals: {{ portals | tojson }}
""",
        encoding="utf-8",
    )

    document = yaml_infra_support.load_yaml_dict(file_path, "test-yaml")

    assert warnings == []
    assert document is not None
    assert document["asset_group"]["name"] == "ga4_data_quality"
    assert document["dq_checks"][0]["portals"] == "__PCG_JINJA_EXPR__"

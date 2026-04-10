"""Unit tests for shared-projection tuning report queries."""

from __future__ import annotations

from platform_context_graph.query import shared_projection_tuning


def test_build_tuning_report_returns_default_scenarios() -> None:
    """The default report should carry the stable scenario matrix."""

    report = shared_projection_tuning.build_tuning_report()

    assert report["projection_domains"] == [
        "repo_dependency",
        "workload_dependency",
    ]
    assert [scenario["setting"] for scenario in report["scenarios"]] == [
        "1x1",
        "2x1",
        "4x1",
        "4x2",
    ]
    assert report["recommended"]["setting"] == "4x2"
    assert report["recommended"]["round_count"] == 2


def test_build_tuning_report_can_include_platform_domain() -> None:
    """Platform mode should prepend the platform shared domain."""

    report = shared_projection_tuning.build_tuning_report(include_platform=True)

    assert report["projection_domains"][0] == "platform_infra"


def test_format_tuning_report_table_renders_recommendation() -> None:
    """The shared table formatter should render the key report summary."""

    report = {
        "projection_domains": ["repo_dependency", "workload_dependency"],
        "scenarios": [
            {
                "setting": "4x2",
                "round_count": 2,
                "mean_processed_per_round": 16.0,
                "peak_pending_total": 32,
            }
        ],
        "recommended": {
            "setting": "4x2",
            "round_count": 2,
            "mean_processed_per_round": 16.0,
        },
    }

    output = shared_projection_tuning.format_tuning_report_table(report)

    assert "Shared Projection Tuning Report" in output
    assert "Setting" in output
    assert "4x2" in output
    assert "Recommended setting: 4x2" in output

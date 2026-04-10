"""Formatting helpers for shared-projection tuning reports."""

from __future__ import annotations


def format_tuning_report_table(report: dict[str, object]) -> str:
    """Render one readable table-oriented tuning report payload."""

    scenarios = list(report.get("scenarios") or [])
    lines = [
        "Shared Projection Tuning Report",
        f"Projection domains: {', '.join(report.get('projection_domains') or [])}",
        "",
        f"{'Setting':<10} {'Rounds':<8} {'Mean/round':<12} {'Peak backlog':<13}",
        f"{'-' * 10} {'-' * 8} {'-' * 12} {'-' * 13}",
    ]
    for scenario in scenarios:
        normalized = dict(scenario)
        lines.append(
            f"{normalized.get('setting', 'n/a'):<10} "
            f"{normalized.get('round_count', 'n/a'):<8} "
            f"{normalized.get('mean_processed_per_round', 'n/a'):<12} "
            f"{normalized.get('peak_pending_total', ''):<13}"
        )
    recommended = dict(report.get("recommended") or {})
    lines.extend(
        [
            "",
            "Recommended setting: "
            f"{recommended.get('setting', 'n/a')} "
            f"(rounds={recommended.get('round_count', 'n/a')}, "
            f"mean_per_round={recommended.get('mean_processed_per_round', 'n/a')})",
        ]
    )
    return "\n".join(lines) + "\n"

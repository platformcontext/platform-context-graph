"""Validate graph-backed end-to-end language support for one local repository."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]

_LANGUAGE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "javascript": (".js", ".mjs", ".cjs", ".jsx"),
    "python": (".py",),
    "typescript": (".ts", ".mts", ".cts"),
    "typescriptjsx": (".tsx",),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for end-to-end support validation."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate graph-backed language support for one local repository "
            "using checkpoint status plus repo context/summary/story queries."
        )
    )
    parser.add_argument(
        "--repo-path",
        required=True,
        help="Absolute path of the local repository that was indexed.",
    )
    parser.add_argument(
        "--language",
        required=True,
        choices=sorted(_LANGUAGE_SUFFIXES),
        help=(
            "Language lane to validate "
            "(javascript, python, typescript, typescriptjsx)."
        ),
    )
    parser.add_argument(
        "--repo-name",
        help="Repository name in the graph. Defaults to the basename of --repo-path.",
    )
    parser.add_argument(
        "--require-framework-evidence",
        action="store_true",
        help="Fail validation when framework_summary or Frameworks story evidence is absent.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Return a non-zero exit code when validation expectations are not met.",
    )
    return parser.parse_args(argv)


def _ensure_repo_src_on_path() -> None:
    """Add the repository ``src`` directory to ``sys.path`` when needed."""

    src_path = str(REPO_ROOT / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _repo_name_from_args(args: argparse.Namespace) -> str:
    """Return the repository name that graph-backed queries should use."""

    if args.repo_name:
        return str(args.repo_name).strip()
    return Path(args.repo_path).resolve().name


def _count_indexed_language_files(
    database: Any,
    *,
    repo_id: str,
    language: str,
) -> int:
    """Count indexed files for one language lane in one repository."""

    suffixes = _LANGUAGE_SUFFIXES[language]
    from platform_context_graph.core import get_database_manager

    db_manager = get_database_manager() if database is None else database
    query = (
        "MATCH (r:Repository {id: $repo_id})-[:REPO_CONTAINS]->(f:File)\n"
        "RETURN f.relative_path AS relative_path"
    )
    with db_manager.get_driver().session() as session:
        rows = session.run(query, repo_id=repo_id).data()
    return sum(
        1
        for row in rows
        if isinstance(row.get("relative_path"), str)
        and str(row["relative_path"]).endswith(suffixes)
    )


def _build_validation_report(args: argparse.Namespace) -> dict[str, Any]:
    """Return the end-to-end validation report for one repository."""

    _ensure_repo_src_on_path()
    from platform_context_graph.core import get_database_manager
    from platform_context_graph.indexing.coordinator import describe_index_run
    from platform_context_graph.mcp.tools.handlers import ecosystem
    from platform_context_graph.query import repositories as repository_queries

    repo_path = str(Path(args.repo_path).resolve())
    repo_name = _repo_name_from_args(args)
    db = get_database_manager()
    index_run = describe_index_run(repo_path)
    context = repository_queries.get_repository_context(db, repo_id=repo_name)
    summary = ecosystem.get_repo_summary(db, repo_name)
    story = repository_queries.get_repository_story(db, repo_id=repo_name)
    repository = dict(context.get("repository") or {})
    repo_id = str(repository.get("id") or "")
    indexed_file_count = (
        _count_indexed_language_files(db, repo_id=repo_id, language=args.language)
        if repo_id
        else 0
    )
    framework_section = next(
        (
            section
            for section in list(story.get("story_sections") or [])
            if isinstance(section, dict) and section.get("id") == "frameworks"
        ),
        None,
    )
    return {
        "repo_path": repo_path,
        "repo_name": repo_name,
        "language": args.language,
        "index_run": index_run,
        "indexed_file_count": indexed_file_count,
        "context_error": context.get("error"),
        "summary_error": summary.get("error"),
        "story_error": story.get("error"),
        "context_framework_summary_present": bool(context.get("framework_summary")),
        "summary_framework_summary_present": bool(summary.get("framework_summary")),
        "story_framework_section_present": framework_section is not None,
        "context_framework_story": context.get("framework_story"),
        "summary_story_head": list(summary.get("story") or [])[:3],
        "story_head": list(story.get("story") or [])[:5],
    }


def _validate_report(
    report: dict[str, Any],
    *,
    require_framework_evidence: bool,
) -> list[str]:
    """Return validation errors for one end-to-end support report."""

    errors: list[str] = []
    index_run = report.get("index_run")
    if not isinstance(index_run, dict):
        errors.append("no completed index run was found for the repository path")
    else:
        if index_run.get("status") != "completed":
            errors.append("index run did not complete cleanly")
        if index_run.get("finalization_status") != "completed":
            errors.append("index finalization did not complete cleanly")

    if int(report.get("indexed_file_count") or 0) <= 0:
        errors.append("no indexed files were found for the requested language")

    for key, label in (
        ("context_error", "repo context"),
        ("summary_error", "repo summary"),
        ("story_error", "repo story"),
    ):
        value = report.get(key)
        if isinstance(value, str) and value.strip():
            errors.append(f"{label} returned an error: {value}")

    if require_framework_evidence:
        if not report.get("context_framework_summary_present"):
            errors.append(
                "framework evidence was required but context lacked framework_summary"
            )
        if not report.get("summary_framework_summary_present"):
            errors.append(
                "framework evidence was required but summary lacked framework_summary"
            )
        if not report.get("story_framework_section_present"):
            errors.append(
                "framework evidence was required but story lacked Frameworks section"
            )
    return errors


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Render one end-to-end language support report and optionally enforce it."""

    args = parse_args(argv)
    success_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr

    report = _build_validation_report(args)
    errors = _validate_report(
        report,
        require_framework_evidence=bool(args.require_framework_evidence),
    )
    if args.check and errors:
        print("Language support validation failed:", file=error_stream)
        for error in errors:
            print(f"- {error}", file=error_stream)
        return 1

    print(json.dumps(report, indent=2), file=success_stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

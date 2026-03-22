from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "docs"
PUBLIC_DOCS_ROOT = DOCS_ROOT / "docs"
MKDOCS_CONFIG = DOCS_ROOT / "mkdocs.yml"
INVENTORY_DOC = DOCS_ROOT / "internal" / "docs-inventory.md"
ARCHIVE_ROOT = DOCS_ROOT / "archive"
INTERNAL_ROOT = DOCS_ROOT / "internal"
README_FILE = REPO_ROOT / "README.md"

REQUIRED_TOP_LEVEL_SECTIONS = [
    "Home",
    "Get Started",
    "Deploy",
    "Guides",
    "API & MCP",
    "Reference",
    "Project",
]

KEBAB_CASE_STEM = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STALE_PUBLIC_STRINGS = ("website/", "vercel", "Vercel", "cd website")


def _iter_public_docs() -> list[Path]:
    return sorted(PUBLIC_DOCS_ROOT.rglob("*.md"))


def _load_nav() -> list[object]:
    raw = MKDOCS_CONFIG.read_text()
    match = re.search(
        r"^nav:\n(?P<nav>.*?)(?=^markdown_extensions:)", raw, re.MULTILINE | re.DOTALL
    )
    assert match is not None, "mkdocs.yml must contain a nav block"
    config = yaml.safe_load("nav:\n" + match.group("nav"))
    return config["nav"]


def _flatten_nav(items: Iterable[object]) -> tuple[list[str], list[str]]:
    labels: list[str] = []
    paths: list[str] = []

    for item in items:
        if isinstance(item, dict):
            for label, value in item.items():
                labels.append(label)
                if isinstance(value, str):
                    paths.append(value)
                else:
                    nested_labels, nested_paths = _flatten_nav(value)
                    labels.extend(nested_labels)
                    paths.extend(nested_paths)

    return labels, paths


def _relative_to_repo(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _assert_kebab_case(path: Path) -> None:
    relative = path.relative_to(PUBLIC_DOCS_ROOT)
    for part in relative.parts[:-1]:
        assert re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", part
        ), f"directory component must be kebab-case: {relative.as_posix()}"

    stem = path.stem
    assert stem == "index" or KEBAB_CASE_STEM.fullmatch(
        stem
    ), f"markdown file must be kebab-case: {relative.as_posix()}"


def test_inventory_exists_and_classifies_every_public_doc() -> None:
    assert INVENTORY_DOC.exists(), "docs/internal/docs-inventory.md must exist"

    inventory = INVENTORY_DOC.read_text()
    for page in _iter_public_docs():
        assert (
            _relative_to_repo(page) in inventory
        ), f"inventory must classify {_relative_to_repo(page)}"


def test_public_docs_live_under_docs_docs_and_use_kebab_case() -> None:
    for page in _iter_public_docs():
        _assert_kebab_case(page)

    _, nav_paths = _flatten_nav(_load_nav())
    for nav_path in nav_paths:
        assert nav_path == nav_path.lower(), f"nav path must be lower-case: {nav_path}"
        assert "_" not in nav_path, f"nav path must not use underscores: {nav_path}"
        assert (
            "README.md" not in nav_path
        ), f"nav path must not use README.md aliases: {nav_path}"


def test_archive_and_internal_boundaries_are_present_and_not_public() -> None:
    assert ARCHIVE_ROOT.exists(), "docs/archive must exist"
    assert INTERNAL_ROOT.exists(), "docs/internal must exist"

    _, nav_paths = _flatten_nav(_load_nav())
    joined_nav = "\n".join(nav_paths)
    assert "archive/" not in joined_nav
    assert "internal/" not in joined_nav


def test_public_docs_and_readme_do_not_reference_ghost_website_flows() -> None:
    for page in _iter_public_docs():
        content = page.read_text()
        for needle in STALE_PUBLIC_STRINGS:
            assert needle not in content, (
                f"public doc still references stale website/Vercel flow: "
                f"{_relative_to_repo(page)} -> {needle}"
            )

    readme = README_FILE.read_text()
    for needle in STALE_PUBLIC_STRINGS:
        assert (
            needle not in readme
        ), f"README still references stale website/Vercel flow: {needle}"


def test_required_information_architecture_exists() -> None:
    nav = _load_nav()
    top_level_labels = [next(iter(item)) for item in nav if isinstance(item, dict)]
    assert top_level_labels == REQUIRED_TOP_LEVEL_SECTIONS


def test_readme_matches_docs_first_product_story() -> None:
    readme = README_FILE.read_text()

    assert "# PlatformContextGraph" in readme
    assert "Code-to-cloud context graph" in readme
    assert "Quick Navigation" in readme
    assert "CLI" in readme
    assert "MCP" in readme
    assert "HTTP API" in readme
    assert "Deploy" in readme
    assert "img.shields.io" in readme
    assert "MCP Compatible" in readme

    assert "## Acknowledgment" in readme
    assert readme.index("## Acknowledgment") > readme.index("## Quick Start")

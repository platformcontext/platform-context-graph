#!/usr/bin/env python3
"""Support code for templated repo inventory reporting."""

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from glob import glob
from pathlib import Path
from typing import Callable, Iterable, TextIO

from platform_context_graph.tools.languages.templated_detection import (
    classify_file,
    FileClassification,
    GENERATED_DIRS,
    is_candidate_text_file,
)

DEFAULT_ROOT_SPECS_ENV_VAR = "TEMPLATED_REPO_DEFAULT_ROOT_SPECS"

ALL_BUCKETS = (
    "plain_text",
    "plain_yaml",
    "go_template_yaml",
    "jinja_yaml",
    "terraform_hcl",
    "terraform_hcl_templated",
    "helm_helper_tpl",
    "unknown_templated",
)
EXAMPLE_BUCKETS = (
    "plain_text",
    "go_template_yaml",
    "jinja_yaml",
    "terraform_hcl_templated",
    "helm_helper_tpl",
    "unknown_templated",
)


def _load_default_root_specs() -> tuple[tuple[str, str], ...]:
    """Load default root specs from an optional environment variable."""

    raw_specs = os.getenv(DEFAULT_ROOT_SPECS_ENV_VAR)
    if not raw_specs:
        return ()
    try:
        parsed = json.loads(raw_specs)
    except (TypeError, ValueError):
        return ()

    specs: list[tuple[str, str]] = []
    for item in parsed:
        if isinstance(item, dict):
            family = item.get("family")
            pattern = item.get("pattern")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            family, pattern = item
        else:
            continue
        if family and pattern:
            specs.append((str(family), str(pattern)))
    return tuple(specs)


DEFAULT_ROOT_SPECS = _load_default_root_specs()


@dataclass(frozen=True, slots=True)
class ScanRoot:
    """Describe one repo root to inventory."""

    name: str
    path: Path
    family: str


@dataclass(frozen=True, slots=True)
class RootInventory:
    """Summarize one scanned root."""

    name: str
    path: Path
    family: str
    buckets: dict[str, int]
    artifact_types: dict[str, int]
    iac_relevant_files: int
    raw_ingest_gap_files: int
    examples: tuple[FileClassification, ...]
    iac_examples: tuple[FileClassification, ...]
    raw_ingest_examples: tuple[FileClassification, ...]
    ambiguous_files: tuple[FileClassification, ...]
    excluded_path_counts: dict[str, int]


def build_scan_roots(
    custom_roots: Iterable[str],
    *,
    family_override: str | None,
) -> tuple[ScanRoot, ...]:
    """Build the set of roots to scan for the current invocation."""

    if custom_roots:
        return tuple(
            ScanRoot(
                name=Path(raw_path).name,
                path=Path(raw_path),
                family=family_override or infer_family_from_path(Path(raw_path)),
            )
            for raw_path in custom_roots
        )

    roots: list[ScanRoot] = []
    for family, pattern in DEFAULT_ROOT_SPECS:
        for expanded in sorted(glob(pattern)):
            path = Path(expanded)
            if path.is_dir():
                roots.append(ScanRoot(name=path.name, path=path, family=family))
    return tuple(roots)


def infer_family_from_path(path: Path) -> str:
    """Infer a default family from a custom root path."""

    path_text = str(path)
    name = path.name
    if "ansible-automate" in path_text:
        return "ansible_jinja"
    if name == "bg-dagster":
        return "dagster_jinja"
    if "terraform-modules" in path_text or name.startswith("terraform"):
        return "terraform"
    if "iac-eks" in name or "argocd" in name:
        return "helm_argo"
    return "generic"


def scan_root(
    root: ScanRoot,
    *,
    max_examples: int,
    include_generated: bool,
    candidate_files: Iterable[Path] | None = None,
) -> RootInventory:
    """Scan one repo root and summarize its authored files."""

    buckets = {bucket: 0 for bucket in ALL_BUCKETS}
    artifact_types: Counter[str] = Counter()
    excluded_counts: Counter[str] = Counter()
    classifications: list[FileClassification] = []

    if candidate_files is None:
        candidate_files = iter_candidate_files(
            root.path,
            include_generated=include_generated,
            excluded_counts=excluded_counts,
        )

    for absolute_path in candidate_files:
        try:
            content = absolute_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            excluded_counts["__read_error__"] += 1
            continue
        classification = classify_file(
            root_family=root.family,
            relative_path=absolute_path.relative_to(root.path),
            content=content,
        )
        buckets[classification.bucket] += 1
        artifact_types[classification.artifact_type] += 1
        classifications.append(classification)

    ambiguous_files = tuple(
        sorted(
            (item for item in classifications if item.ambiguous),
            key=lambda item: str(item.relative_path),
        )
    )
    examples = tuple(select_examples(classifications, max_examples=max_examples))
    iac_examples = tuple(
        select_filtered_examples(
            classifications,
            max_examples=max_examples,
            predicate=lambda item: item.iac_relevant,
        )
    )
    raw_ingest_examples = tuple(
        select_filtered_examples(
            classifications,
            max_examples=max_examples,
            predicate=lambda item: item.raw_ingest_candidate,
        )
    )

    return RootInventory(
        name=root.name,
        path=root.path,
        family=root.family,
        buckets=buckets,
        artifact_types=dict(sorted(artifact_types.items())),
        iac_relevant_files=sum(1 for item in classifications if item.iac_relevant),
        raw_ingest_gap_files=sum(
            1 for item in classifications if item.raw_ingest_candidate
        ),
        examples=examples,
        iac_examples=iac_examples,
        raw_ingest_examples=raw_ingest_examples,
        ambiguous_files=ambiguous_files,
        excluded_path_counts=dict(sorted(excluded_counts.items())),
    )


def iter_candidate_files(
    root: Path,
    *,
    include_generated: bool,
    excluded_counts: Counter[str],
) -> Iterable[Path]:
    """Yield candidate text files beneath a repo root."""

    for directory, dirnames, filenames in os.walk(root):
        current = Path(directory)
        if not include_generated:
            kept_dirnames: list[str] = []
            for dirname in sorted(dirnames):
                if dirname in GENERATED_DIRS:
                    excluded_total = count_candidate_files(current / dirname)
                    if excluded_total:
                        excluded_counts[dirname] += excluded_total
                    continue
                kept_dirnames.append(dirname)
            dirnames[:] = kept_dirnames
        for filename in sorted(filenames):
            path = current / filename
            if is_candidate_text_file(path):
                yield path


def count_candidate_files(root: Path) -> int:
    """Count candidate text files beneath an excluded subtree."""

    total = 0
    for directory, _dirnames, filenames in os.walk(root):
        current = Path(directory)
        total += sum(
            1 for filename in filenames if is_candidate_text_file(current / filename)
        )
    return total


def select_examples(
    classifications: Iterable[FileClassification], *, max_examples: int
) -> list[FileClassification]:
    """Select representative examples for templated buckets only."""

    by_bucket: dict[str, list[FileClassification]] = {bucket: [] for bucket in EXAMPLE_BUCKETS}
    for classification in classifications:
        if classification.bucket in by_bucket:
            by_bucket[classification.bucket].append(classification)

    examples: list[FileClassification] = []
    for bucket in EXAMPLE_BUCKETS:
        if len(examples) >= max_examples:
            break
        candidates = sorted(
            by_bucket[bucket],
            key=lambda item: (-item.marker_count, -item.marker_density, str(item.relative_path)),
        )
        if candidates:
            examples.append(candidates[0])
    return examples


def select_filtered_examples(
    classifications: Iterable[FileClassification],
    *,
    max_examples: int,
    predicate: Callable[[FileClassification], bool],
) -> list[FileClassification]:
    """Select representative examples from a filtered subset."""

    candidates = sorted(
        (item for item in classifications if predicate(item)),
        key=lambda item: (-item.marker_count, -item.marker_density, str(item.relative_path)),
    )
    return candidates[:max_examples]


def emit_console_report(inventories: Iterable[RootInventory], *, stdout: TextIO) -> None:
    """Write a compact human-readable summary."""

    for inventory in inventories:
        stdout.write(f"{inventory.name} [{inventory.family}] {inventory.path}\n")
        bucket_summary = ", ".join(
            f"{bucket}={count}" for bucket, count in inventory.buckets.items() if count
        ) or "no classified files"
        stdout.write(f"  buckets: {bucket_summary}\n")
        artifact_summary = ", ".join(
            f"{artifact}={count}"
            for artifact, count in inventory.artifact_types.items()
            if count
        )
        if artifact_summary:
            stdout.write(f"  artifacts: {artifact_summary}\n")
        stdout.write(
            "  coverage: "
            f"iac_relevant_files={inventory.iac_relevant_files}, "
            f"raw_ingest_gap_files={inventory.raw_ingest_gap_files}\n"
        )
        if inventory.excluded_path_counts:
            excluded_summary = ", ".join(
                f"{name}={count}" for name, count in inventory.excluded_path_counts.items()
            )
            stdout.write(f"  excluded: {excluded_summary}\n")
        if inventory.examples:
            stdout.write("  examples:\n")
            for example in inventory.examples:
                stdout.write(
                    f"    - {example.relative_path} [{example.bucket}] "
                    f"markers={example.marker_count} "
                    f"dialects={','.join(example.dialects) or 'none'} "
                    f"artifact={example.artifact_type}\n"
                )
        if inventory.raw_ingest_examples:
            stdout.write("  raw-ingest gaps:\n")
            for example in inventory.raw_ingest_examples:
                stdout.write(
                    f"    - {example.relative_path} "
                    f"artifact={example.artifact_type} "
                    f"dialects={','.join(example.dialects) or 'none'}\n"
                )
        if inventory.iac_examples:
            stdout.write("  iac highlights:\n")
            for example in inventory.iac_examples:
                stdout.write(
                    f"    - {example.relative_path} "
                    f"artifact={example.artifact_type} "
                    f"bucket={example.bucket}\n"
                )
        if inventory.ambiguous_files:
            stdout.write("  ambiguous:\n")
            for item in inventory.ambiguous_files:
                stdout.write(
                    f"    - {item.relative_path} dialects={','.join(item.dialects)}\n"
                )


def write_json_report(inventories: Iterable[RootInventory], *, output_path: Path) -> None:
    """Write the machine-readable JSON artifact."""

    payload = {"roots": [root_inventory_to_json(item) for item in inventories]}
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def root_inventory_to_json(inventory: RootInventory) -> dict[str, object]:
    """Convert a root inventory into a JSON-compatible dictionary."""

    return {
        "name": inventory.name,
        "path": str(inventory.path),
        "family": inventory.family,
        "buckets": inventory.buckets,
        "artifact_types": inventory.artifact_types,
        "iac_relevant_files": inventory.iac_relevant_files,
        "raw_ingest_gap_files": inventory.raw_ingest_gap_files,
        "examples": [classification_to_json(item) for item in inventory.examples],
        "iac_examples": [classification_to_json(item) for item in inventory.iac_examples],
        "raw_ingest_examples": [
            classification_to_json(item) for item in inventory.raw_ingest_examples
        ],
        "ambiguous_files": [
            classification_to_json(item) for item in inventory.ambiguous_files
        ],
        "excluded_path_counts": inventory.excluded_path_counts,
    }


def classification_to_json(classification: FileClassification) -> dict[str, object]:
    """Convert a file classification into a JSON-compatible dictionary."""

    payload = asdict(classification)
    payload["relative_path"] = str(classification.relative_path)
    payload["dialects"] = list(classification.dialects)
    return payload

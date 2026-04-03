"""SCIP runner and language-detection helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from ...utils.debug_log import info_logger, warning_logger

EXTENSION_TO_SCIP: dict[str, tuple[str, str, str]] = {
    ".py": ("python", "scip-python", "pip install scip-python"),
    ".ipynb": ("python", "scip-python", "pip install scip-python"),
    ".ts": (
        "typescript",
        "scip-typescript",
        "npm install -g @sourcegraph/scip-typescript",
    ),
    ".tsx": (
        "typescript",
        "scip-typescript",
        "npm install -g @sourcegraph/scip-typescript",
    ),
    ".js": (
        "javascript",
        "scip-typescript",
        "npm install -g @sourcegraph/scip-typescript",
    ),
    ".jsx": (
        "javascript",
        "scip-typescript",
        "npm install -g @sourcegraph/scip-typescript",
    ),
    ".go": ("go", "scip-go", "go install github.com/sourcegraph/scip-go/...@latest"),
    ".rs": ("rust", "scip-rust", "cargo install scip-rust"),
    ".java": ("java", "scip-java", "see https://github.com/sourcegraph/scip-java"),
    ".cpp": ("cpp", "scip-clang", "brew install llvm"),
    ".hpp": ("cpp", "scip-clang", "brew install llvm"),
    ".c": ("c", "scip-clang", "brew install llvm"),
    ".h": ("cpp", "scip-clang", "brew install llvm"),
}


def is_scip_available(lang: str) -> bool:
    """Return whether the SCIP indexer for a language is installed.

    Args:
        lang: Language name to check.

    Returns:
        ``True`` when an appropriate SCIP binary is available.
    """

    for mapped_lang, binary, _install_hint in EXTENSION_TO_SCIP.values():
        if mapped_lang == lang:
            return shutil.which(binary) is not None
    return False


def detect_project_lang(path: Path, scip_languages: List[str]) -> Optional[str]:
    """Detect the dominant SCIP-capable language in a path.

    Args:
        path: Project directory or file path.
        scip_languages: Allowed SCIP languages from configuration.

    Returns:
        Detected language name when one is available, otherwise ``None``.
    """

    if not path.is_dir():
        lang = EXTENSION_TO_SCIP.get(path.suffix, (None, "", ""))[0]
        return lang if lang in scip_languages else None

    counts: dict[str, int] = {}
    for ext, (lang, _binary, _install_hint) in EXTENSION_TO_SCIP.items():
        if lang not in scip_languages:
            continue
        counts[lang] = counts.get(lang, 0) + sum(1 for _ in path.rglob(f"*{ext}"))
    if not counts:
        return None
    return max(counts, key=counts.__getitem__)


class ScipIndexer:
    """Run the appropriate ``scip-*`` CLI for a project directory."""

    def run(self, project_path: Path, lang: str, output_dir: Path) -> Optional[Path]:
        """Execute a SCIP indexer and return the resulting index path.

        Args:
            project_path: Project directory to index.
            lang: Detected language name.
            output_dir: Temporary output directory.

        Returns:
            Path to ``index.scip`` when indexing succeeds, otherwise ``None``.
        """

        binary, install_hint = self._get_binary(lang)
        if not binary:
            warning_logger(
                f"SCIP indexer for '{lang}' not found. Install with: {install_hint}"
            )
            return None

        output_file = output_dir / "index.scip"
        command = self._build_command(lang, binary, output_file)
        if not command:
            warning_logger(f"No SCIP command template defined for language: {lang}")
            return None

        info_logger(f"Running SCIP indexer: {' '.join(str(item) for item in command)}")
        try:
            result = subprocess.run(
                command,
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            warning_logger("SCIP indexer timed out after 5 minutes.")
            return None
        except Exception as exc:  # pragma: no cover - subprocess boundary
            warning_logger(f"SCIP indexer failed with exception: {exc}")
            return None

        if result.returncode != 0:
            warning_logger(
                "SCIP indexer exited with code "
                f"{result.returncode}.\nstderr: {result.stderr[:500]}"
            )
            return None
        if not output_file.exists():
            warning_logger(
                f"SCIP indexer ran but no index.scip produced at {output_file}"
            )
            return None

        info_logger(
            "SCIP index written to "
            f"{output_file} ({output_file.stat().st_size // 1024} KB)"
        )
        return output_file

    def _get_binary(self, lang: str) -> Tuple[Optional[str], str]:
        """Resolve the CLI binary and install hint for a language.

        Args:
            lang: Detected language name.

        Returns:
            Tuple of resolved binary path and install hint.
        """

        for mapped_lang, binary, install_hint in EXTENSION_TO_SCIP.values():
            if mapped_lang == lang:
                return shutil.which(binary), install_hint
        return None, "unknown language"

    def _build_command(
        self,
        lang: str,
        binary: str,
        output_file: Path,
    ) -> Optional[list[str]]:
        """Build the SCIP CLI command for a language.

        Args:
            lang: Detected language name.
            binary: Resolved SCIP CLI binary.
            output_file: Destination ``index.scip`` file.

        Returns:
            CLI argument vector when supported, otherwise ``None``.
        """

        output_path = str(output_file)
        if lang == "python":
            return [binary, "index", ".", "--output", output_path]
        if lang in ("typescript", "javascript"):
            return [binary, "index", "--output", output_path]
        if lang == "go":
            return [binary, "--output", output_path]
        if lang == "rust":
            return [binary, "index", "--output", output_path]
        if lang == "java":
            return [binary, "index", "--output", output_path]
        if lang in ("cpp", "c"):
            return [binary, f"--index-output-path={output_path}"]
        return None

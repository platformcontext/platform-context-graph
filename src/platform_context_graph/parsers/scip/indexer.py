"""Canonical SCIP parser/runtime exports."""

from __future__ import annotations

import os

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from .parser import ScipIndexParser
from .support import (
    EXTENSION_TO_SCIP,
    ScipIndexer,
    detect_project_lang,
    is_scip_available,
)

__all__ = [
    "EXTENSION_TO_SCIP",
    "ScipIndexer",
    "ScipIndexParser",
    "detect_project_lang",
    "is_scip_available",
]

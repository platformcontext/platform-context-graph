"""Public SCIP indexing entrypoints and compatibility facade."""

from __future__ import annotations

import os

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from .scip_parser import ScipIndexParser
from .scip_support import (
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

"""Filesystem paths for PlatformContextGraph."""

from __future__ import annotations

import os
from pathlib import Path

APP_HOME_ENV_VAR = "PCG_HOME"
APP_HOME_DIRNAME = ".platform-context-graph"
APP_HOME_DISPLAY = "~/.platform-context-graph"


def get_app_home() -> Path:
    """Return the preferred application home."""
    configured = os.getenv(APP_HOME_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / APP_HOME_DIRNAME


def get_app_env_file() -> Path:
    """Return the global environment/config file path."""
    return get_app_home() / ".env"

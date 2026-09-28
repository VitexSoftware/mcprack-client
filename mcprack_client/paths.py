"""Path helpers for mcprack sync state files."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg_state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))


def state_dir() -> Path:
    path = _xdg_state_home() / "mcprack-sync"
    path.mkdir(parents=True, exist_ok=True)
    return path


def managed_state_path(tool: str) -> Path:
    return state_dir() / f"{tool}.managed.json"

"""Shared helpers for mcprack MCP client config sync tools.

Stdlib-only — no Flask, no requests. Used by mcprack-sync-claude,
mcprack-sync-cursor, and mcprack-sync-vscode.
"""

__version__ = "1.0.0"

from .api import McprackApiError, fetch_client_config
from .config import ClientSettings, load_settings, save_settings
from .merge import MergeResult, merge_mcp_config
from .paths import state_dir
from .write import atomic_write_json, load_json_file

__all__ = [
    "ClientSettings",
    "McprackApiError",
    "MergeResult",
    "atomic_write_json",
    "fetch_client_config",
    "load_json_file",
    "load_settings",
    "merge_mcp_config",
    "save_settings",
    "state_dir",
]

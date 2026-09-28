"""Merge remote mcprack server maps into an existing client config file."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MergeResult:
    config: dict[str, Any]
    managed_names: list[str]
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


def _server_map_from_remote(remote: dict[str, Any], servers_key: str) -> dict[str, Any]:
    if servers_key in remote and isinstance(remote[servers_key], dict):
        return dict(remote[servers_key])
    # tolerate accidental nesting / alternate key
    for alt in ("mcpServers", "servers"):
        if alt in remote and isinstance(remote[alt], dict):
            return dict(remote[alt])
    return {}


def merge_mcp_config(
    existing: dict[str, Any] | None,
    remote: dict[str, Any],
    *,
    servers_key: str,
    previously_managed: list[str] | set[str] | None = None,
    replace_all: bool = False,
) -> MergeResult:
    """Merge remote mcp server entries into an existing client config.

    - Upserts every server from the remote map under ``servers_key``.
    - Removes servers that were previously managed by mcprack but are no
      longer in the remote selection (unless ``replace_all``).
    - With ``replace_all``, the entire ``servers_key`` map is replaced.
    - All other top-level keys (preferences, etc.) are preserved.
    """
    base: dict[str, Any] = dict(existing or {})
    remote_servers = _server_map_from_remote(remote, servers_key)
    previous = set(previously_managed or [])

    if replace_all:
        local_servers: dict[str, Any] = {}
        preserved: list[str] = []
    else:
        current = base.get(servers_key)
        local_servers = dict(current) if isinstance(current, dict) else {}
        preserved = sorted(name for name in local_servers if name not in previous)

    added: list[str] = []
    updated: list[str] = []
    removed: list[str] = []

    if not replace_all:
        for name in sorted(previous):
            if name not in remote_servers and name in local_servers:
                del local_servers[name]
                removed.append(name)

    for name, entry in remote_servers.items():
        if name not in local_servers:
            added.append(name)
        elif local_servers[name] != entry:
            updated.append(name)
        local_servers[name] = entry

    base[servers_key] = local_servers
    managed = sorted(remote_servers.keys())
    return MergeResult(
        config=base,
        managed_names=managed,
        added=sorted(added),
        updated=sorted(updated),
        removed=sorted(removed),
        preserved=preserved,
    )

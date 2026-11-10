"""Refuse server entries a legitimate mcprack never sends.

The sync tools write whatever mcprack answers into the user's own client
configuration - `~/.claude.json`, Cursor's and VS Code's `mcp.json`. For Claude
Code and the others an entry with `command`/`args` is not a description, it is
*a program the client will run*, on every workstation that syncs, without a
prompt (user-scope servers are not approved one by one). A compromised or
malicious mcprack - or anybody who can alter the response on a plain-HTTP hop -
could otherwise turn "sync my servers" into code execution on all of them
(docs/AUDIT-2026-11.md D-01).

What mcprack really sends is small and fixed: a name, `type` http/sse, a `url`
on its own origin, and at most `headers`. Anything else is refused, as a whole:
a config that fails validation is not written at all.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from .merge import _server_map_from_remote

ALLOWED_KEYS = frozenset({"type", "url", "headers"})
ALLOWED_TYPES = frozenset({"http", "sse"})
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_DEFAULT_PORTS = {"http": 80, "https": 443}
MAX_HEADER_VALUE = 4096
# RFC 7230 "token": what a header *name* may consist of.
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
# Claude Code, Cursor and VS Code expand ${VAR} / ${env:VAR} in a server's `url`
# and `headers` from the *user's* environment. In text that comes from the server
# that is a read primitive: `X-Leak: ${AWS_SECRET_ACCESS_KEY}` would deliver the
# value to whoever answered the sync. The one placeholder mcprack legitimately
# uses - the user's own token for this very server - is the only exception.
EXPANSION_MARKER = "${"
ALLOWED_PLACEHOLDER_HEADERS = {"authorization": "Bearer ${MCPRACK_TOKEN}"}


class UnsafeConfigError(ValueError):
    """The answer contained something that must not be written to a client config."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def origin_of(url: str) -> tuple[str, str, int] | None:
    """(scheme, host, port) of `url`, or None when it is not an absolute
    http(s) URL with a host."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in _DEFAULT_PORTS or not parts.hostname:
        return None
    return parts.scheme, parts.hostname.lower(), port or _DEFAULT_PORTS[parts.scheme]


def is_loopback(url: str) -> bool:
    origin = origin_of(url)
    return origin is not None and origin[1] in _LOOPBACK


def transport_is_acceptable(url: str, *, allow_insecure: bool) -> bool:
    """The API token is a bearer credential: it only goes over TLS, or to this
    very machine, unless the user said otherwise explicitly."""
    origin = origin_of(url)
    if origin is None:
        return False
    return origin[0] == "https" or origin[1] in _LOOPBACK or allow_insecure


def validate_remote_config(
    remote: dict[str, Any],
    *,
    servers_key: str,
    base_url: str,
    trusted_origins: tuple[str, ...] = (),
    allow_insecure: bool = False,
) -> None:
    """Raise UnsafeConfigError listing every problem, or return None.

    Messages name the server and the offending *key*, never its value: the value
    is attacker-controlled text that ends up on the user's terminal."""
    allowed_origins = set()
    for candidate in (base_url, *trusted_origins):
        origin = origin_of(candidate)
        if origin is not None:
            allowed_origins.add(origin)

    problems: list[str] = []
    servers = _server_map_from_remote(remote, servers_key)
    for name, entry in servers.items():
        label = f"server {name!r}" if _NAME.match(str(name)) else "a server with an unusable name"
        if not isinstance(name, str) or not _NAME.match(name):
            problems.append(f"{label}: name must be 1-64 characters of letters, digits, '.', '_', '-' or space")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{label}: entry is not an object")
            continue

        for key in sorted(set(entry) - ALLOWED_KEYS):
            reason = (
                "would make the client run a program"
                if key in {"command", "args", "env", "cwd", "shell"}
                else "is not something mcprack sends"
            )
            problems.append(f"{label}: unexpected key {key!r} ({reason})")

        if entry.get("type") not in ALLOWED_TYPES:
            problems.append(f"{label}: 'type' must be one of {sorted(ALLOWED_TYPES)}")

        url = entry.get("url")
        if not isinstance(url, str) or origin_of(url) is None:
            problems.append(f"{label}: 'url' must be an absolute http(s) URL")
        else:
            if origin_of(url) not in allowed_origins:
                problems.append(
                    f"{label}: 'url' points to a different origin than mcprack "
                    "(add it to MCPRACK_TRUSTED_ORIGINS if that is expected)"
                )
            if not transport_is_acceptable(url, allow_insecure=allow_insecure):
                problems.append(f"{label}: 'url' is plain http (set MCPRACK_ALLOW_INSECURE=1 on a trusted network)")
            if urlsplit(url).username or urlsplit(url).password:
                problems.append(f"{label}: 'url' carries credentials in its authority part")
            if EXPANSION_MARKER in url:
                problems.append(f"{label}: 'url' contains an environment-variable reference")

        headers = entry.get("headers")
        if headers is not None:
            if not isinstance(headers, dict) or not all(
                isinstance(k, str) and isinstance(v, str) and len(v) <= MAX_HEADER_VALUE and "\n" not in v + k and "\r" not in v + k
                for k, v in headers.items()
            ):
                problems.append(f"{label}: 'headers' must map header names to single-line strings")
            else:
                for header_name, header_value in headers.items():
                    if not _HEADER_NAME.match(header_name):
                        problems.append(f"{label}: a header name contains characters that are not allowed in one")
                    if EXPANSION_MARKER in header_name or (
                        EXPANSION_MARKER in header_value
                        and ALLOWED_PLACEHOLDER_HEADERS.get(header_name.lower()) != header_value
                    ):
                        problems.append(
                            f"{label}: a header contains an environment-variable reference "
                            "(the client would substitute a value from your environment)"
                        )

    if problems:
        raise UnsafeConfigError(problems)

"""Shared argparse CLI factory for the per-client sync wrappers."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .api import McprackApiError, fetch_client_config
from .config import load_settings, save_settings
from .merge import merge_mcp_config
from .paths import managed_state_path
from .validate import UnsafeConfigError, validate_remote_config
from .write import ConcurrentModification, atomic_write_json, file_signature, load_json_file


ResolvePath = Callable[[], Path]


def _load_managed(tool: str) -> list[str]:
    path = managed_state_path(tool)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    names = data.get("managed") if isinstance(data, dict) else None
    if isinstance(names, list):
        return [str(n) for n in names]
    return []


def _save_managed(tool: str, names: list[str], config_path: Path) -> None:
    path = managed_state_path(tool)
    payload = {
        "managed": names,
        "config_path": str(config_path),
    }
    atomic_write_json(path, payload, backup=False)


def build_parser(prog: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description=description)
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Fetch config from mcprack and merge into the local client file")
    sync.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    sync.add_argument(
        "--replace",
        action="store_true",
        help="Replace the entire servers map (do not preserve local-only servers)",
    )
    sync.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Override the target client config path",
    )

    sub.add_parser("status", help="Show settings, target path, and managed server names")

    configure = sub.add_parser("configure", help="Write ~/.config/mcprack/client.env")
    configure.add_argument("--url", required=True, help="mcprack base URL, e.g. https://mcprack.example.com")
    configure.add_argument(
        "--token",
        default=None,
        help="Personal API token (visible in the process list - prefer --token-file, MCPRACK_TOKEN or the prompt)",
    )
    configure.add_argument("--token-file", type=Path, default=None, help="Read the API token from this file (first line)")
    configure.add_argument(
        "--trusted-origin",
        action="append",
        default=[],
        metavar="URL",
        help="Another origin the servers' URLs may point to (mcprack's PUBLIC_BASE_URL, when it differs from --url); repeatable",
    )
    configure.add_argument(
        "--allow-insecure",
        action="store_true",
        help="Send the token over plain http to a non-loopback host (trusted private network only)",
    )

    return parser


def run_cli(
    *,
    prog: str,
    description: str,
    tool: str,
    api_client: str,
    servers_key: str,
    resolve_config_path: ResolvePath,
    argv: Sequence[str] | None = None,
) -> int:
    parser = build_parser(prog, description)
    args = parser.parse_args(argv)

    if args.command == "configure":
        token = args.token
        if token:
            print("warning: --token is visible to other users in the process list; prefer --token-file", file=sys.stderr)
        elif args.token_file:
            token = args.token_file.read_text(encoding="utf-8").splitlines()[0].strip() if args.token_file.stat().st_size else ""
        else:
            token = os.environ.get("MCPRACK_TOKEN", "").strip() or getpass.getpass("mcprack API token (input hidden): ").strip()
        if not token:
            print("No API token given.", file=sys.stderr)
            return 2
        path = save_settings(
            args.url,
            token,
            trusted_origins=tuple(args.trusted_origin),
            allow_insecure=args.allow_insecure,
        )
        print(f"Wrote {path}")
        return 0

    settings = load_settings()
    config_path = args.config if getattr(args, "config", None) else resolve_config_path()

    if args.command == "status":
        managed = _load_managed(tool)
        print(f"settings:  url={settings.url or '(unset)'} source={settings.source}")
        print(f"token:     {'set' if settings.token else 'missing'}")
        print(f"api client:{api_client}")
        print(f"config:    {config_path} ({'exists' if config_path.is_file() else 'missing'})")
        print(f"servers key:{servers_key}")
        print(f"managed:   {', '.join(managed) if managed else '(none yet)'}")
        return 0 if settings.ok() else 1

    # sync
    if not settings.ok():
        print(
            "Missing MCPRACK_URL / MCPRACK_TOKEN. Run "
            f"`{prog} configure --url … --token …` or export them.",
            file=sys.stderr,
        )
        return 2

    try:
        remote = fetch_client_config(
            settings.url, settings.token, api_client, allow_insecure=settings.allow_insecure
        )
    except McprackApiError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # Nothing from the answer is written until every entry has passed: an entry
    # that would make the client run a program, or talk to another host, is a
    # reason to stop - not to skip that one entry and carry on trusting the rest.
    try:
        validate_remote_config(
            remote,
            servers_key=servers_key,
            base_url=settings.url,
            trusted_origins=settings.trusted_origins,
            allow_insecure=settings.allow_insecure,
        )
    except UnsafeConfigError as exc:
        print(f"refusing the answer from {settings.url} - nothing was written:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 3

    def read_and_merge():
        signature = file_signature(config_path)
        existing = load_json_file(config_path)
        return signature, merge_mcp_config(
            existing,
            remote,
            servers_key=servers_key,
            previously_managed=_load_managed(tool),
            replace_all=bool(args.replace),
        )

    try:
        signature, result = read_and_merge()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"target:    {config_path}")
    print(f"remote:    {len(result.managed_names)} server(s) from {settings.url}")
    if result.added:
        print(f"added:     {', '.join(result.added)}")
    if result.updated:
        print(f"updated:   {', '.join(result.updated)}")
    if result.removed:
        print(f"removed:   {', '.join(result.removed)}")
    if result.preserved:
        print(f"preserved: {', '.join(result.preserved)}")
    if not result.changed:
        print("unchanged: local config already matches mcprack selection")

    if args.dry_run:
        print("dry-run:   no files written")
        return 0

    if result.changed or not config_path.is_file():
        # The client (Claude Code rewrites ~/.claude.json all the time) may save
        # while we merge. Writing over it would drop its change, so if the file
        # moved under us, merge again onto what is there now.
        for _attempt in range(3):
            try:
                atomic_write_json(config_path, result.config, backup=True, expect_signature=signature)
                break
            except ConcurrentModification:
                try:
                    signature, result = read_and_merge()
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
                    return 1
        else:
            print(f"{config_path} keeps changing while it is being updated - nothing was written, try again", file=sys.stderr)
            return 1
        print(f"wrote:     {config_path}")
    _save_managed(tool, result.managed_names, config_path)
    return 0

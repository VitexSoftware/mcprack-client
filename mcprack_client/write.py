"""Atomic JSON read/write with optional backup."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


class ConcurrentModification(RuntimeError):
    """The file changed between reading it and replacing it - somebody else
    (typically the running client itself) wrote it in the meantime."""


_UNSET: Any = object()


def file_signature(path: Path) -> tuple[int, int, int] | None:
    """Cheap fingerprint of a file's current state (None when it is absent)."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return st.st_mtime_ns, st.st_size, st.st_ino


def atomic_write_json(
    path: Path,
    data: dict[str, Any],
    *,
    backup: bool = True,
    expect_signature: Any = _UNSET,
) -> None:
    # Write to what the path points at: replacing a symlink (dotfile managers
    # link ~/.claude.json) would silently turn it into a regular file.
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.is_file():
        # The backup of a client config holds everything the original does
        # (~/.claude.json: OAuth tokens, API keys) - create it 0600, never with
        # the umask's mode.
        backup_path = path.with_suffix(path.suffix + ".bak")
        fd = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(path.read_text(encoding="utf-8"))

    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if expect_signature is not _UNSET and file_signature(path) != expect_signature:
            raise ConcurrentModification(f"{path} changed while it was being updated")
        try:
            os.chmod(tmp_name, os.stat(path).st_mode & 0o777)  # keep the file's own permissions
        except FileNotFoundError:
            pass
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

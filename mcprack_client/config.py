"""Load / save mcprack sync client settings (URL + API token)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def default_user_config_path() -> Path:
    return _xdg_config_home() / "mcprack" / "client.env"


def system_config_path() -> Path:
    return Path("/etc/mcprack/client.env")


@dataclass
class ClientSettings:
    url: str
    token: str
    source: str

    def ok(self) -> bool:
        return bool(self.url.strip() and self.token.strip())


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def load_settings(
    *,
    env: dict[str, str] | None = None,
    user_path: Path | None = None,
    system_path: Path | None = None,
) -> ClientSettings:
    """Resolve settings with precedence: process env > user file > system file."""
    environ = env if env is not None else os.environ
    merged: dict[str, str] = {}
    sources: list[str] = []

    sys_path = system_path if system_path is not None else system_config_path()
    usr_path = user_path if user_path is not None else default_user_config_path()

    for path, label in ((sys_path, "system"), (usr_path, "user")):
        parsed = _parse_env_file(path)
        if parsed:
            merged.update(parsed)
            sources.append(f"{label}:{path}")

    for key in ("MCPRACK_URL", "MCPRACK_TOKEN"):
        if key in environ and environ[key].strip():
            merged[key] = environ[key].strip()
            if "env" not in sources:
                sources.append("env")

    return ClientSettings(
        url=(merged.get("MCPRACK_URL") or "").rstrip("/"),
        token=merged.get("MCPRACK_TOKEN") or "",
        source=", ".join(sources) if sources else "none",
    )


def save_settings(
    url: str,
    token: str,
    *,
    path: Path | None = None,
) -> Path:
    """Write user settings file (0600). Creates parent dirs as needed."""
    target = path if path is not None else default_user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# mcprack client sync settings\n"
        f"MCPRACK_URL={url.rstrip('/')}\n"
        f"MCPRACK_TOKEN={token}\n"
    )
    target.write_text(body, encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target

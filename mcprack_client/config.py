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
    # Origins besides MCPRACK_URL that the servers' URLs may point to (mcprack
    # builds them from its PUBLIC_BASE_URL, which can differ from the address
    # this client reaches it on).
    trusted_origins: tuple[str, ...] = ()
    # Send the token over plain http to a host that is not loopback.
    allow_insecure: bool = False

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

    for key in ("MCPRACK_URL", "MCPRACK_TOKEN", "MCPRACK_TRUSTED_ORIGINS", "MCPRACK_ALLOW_INSECURE"):
        if key in environ and environ[key].strip():
            merged[key] = environ[key].strip()
            if "env" not in sources:
                sources.append("env")

    return ClientSettings(
        url=(merged.get("MCPRACK_URL") or "").rstrip("/"),
        token=merged.get("MCPRACK_TOKEN") or "",
        source=", ".join(sources) if sources else "none",
        trusted_origins=tuple(
            item.strip().rstrip("/") for item in (merged.get("MCPRACK_TRUSTED_ORIGINS") or "").split(",") if item.strip()
        ),
        allow_insecure=(merged.get("MCPRACK_ALLOW_INSECURE") or "").strip().lower() in {"1", "true", "yes", "on"},
    )


def save_settings(
    url: str,
    token: str,
    *,
    path: Path | None = None,
    trusted_origins: tuple[str, ...] = (),
    allow_insecure: bool = False,
) -> Path:
    """Write user settings file (0600). Creates parent dirs as needed."""
    target = path if path is not None else default_user_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# mcprack client sync settings",
        f"MCPRACK_URL={url.rstrip('/')}",
        f"MCPRACK_TOKEN={token}",
    ]
    if trusted_origins:
        lines.append(f"MCPRACK_TRUSTED_ORIGINS={','.join(trusted_origins)}")
    if allow_insecure:
        lines.append("MCPRACK_ALLOW_INSECURE=1")
    # Created 0600 from the start - not written with the umask's mode and
    # tightened afterwards, which leaves the token readable for a moment.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write("\n".join(lines) + "\n")
    return target

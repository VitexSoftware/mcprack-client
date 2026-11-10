"""HTTP client for mcprack's /api/v1/me/config/<client> endpoint."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .validate import transport_is_acceptable

# A rendered client config is a few kilobytes. A server (or whoever sits on the
# path) that answers with gigabytes should not be able to exhaust the memory of
# a workstation that merely wanted to sync.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_CLIENT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib re-sends the Authorization header when it follows a redirect -
    also to another host. The token goes where the user configured it and
    nowhere else, so a redirect is reported, never followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def _printable(text: str, limit: int = 300) -> str:
    """Text from the server, made safe to show: no control characters (terminal
    escape sequences), bounded length."""
    return re.sub(r"[^\x20-\x7e\u00a0-\uffff]", "?", text)[:limit]


class McprackApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


def fetch_client_config(
    base_url: str,
    token: str,
    client: str,
    *,
    timeout: float = 30.0,
    allow_insecure: bool = False,
) -> dict[str, Any]:
    """Return the rendered client config object (not the API envelope).

    Expected API response shape:
        {"ok": true, "data": {"filename": "...", "config": {...}}}
    """
    if not _CLIENT_NAME.match(client):
        raise McprackApiError(f"invalid client name {client!r}")
    if not transport_is_acceptable(base_url, allow_insecure=allow_insecure):
        raise McprackApiError(
            "refusing to send the API token over plain http (it would cross the network in clear text): "
            "use an https:// MCPRACK_URL, or set MCPRACK_ALLOW_INSECURE=1 on a trusted private network"
        )
    url = f"{base_url.rstrip('/')}/api/v1/me/config/{client}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "mcprack-client/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise McprackApiError(f"mcprack API answer is larger than {MAX_RESPONSE_BYTES} bytes - refusing it")
        payload = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise McprackApiError(
                f"mcprack API answered with a redirect (HTTP {exc.code}); it is not followed because the API token "
                "must not leave the host you configured - correct MCPRACK_URL",
                status=exc.code,
            ) from exc
        body = ""
        try:
            body = exc.read(2048).decode("utf-8", errors="replace")
        except Exception:
            pass
        detail = _printable(body.strip() or str(exc.reason))
        raise McprackApiError(
            f"mcprack API HTTP {exc.code} for {client}: {detail}",
            status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise McprackApiError(f"mcprack API unreachable at {url}: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise McprackApiError(f"mcprack API returned invalid JSON: {_printable(str(exc))}") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        # tolerate a bare config object for tests / older stubs
        if isinstance(payload, dict) and (
            "mcpServers" in payload or "servers" in payload
        ):
            return payload
        raise McprackApiError("mcprack API response missing data object")

    config = data.get("config")
    if not isinstance(config, dict):
        raise McprackApiError("mcprack API response missing config object")
    return config

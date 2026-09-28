"""HTTP client for mcprack's /api/v1/me/config/<client> endpoint."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


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
) -> dict[str, Any]:
    """Return the rendered client config object (not the API envelope).

    Expected API response shape:
        {"ok": true, "data": {"filename": "...", "config": {...}}}
    """
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        detail = body.strip() or exc.reason
        raise McprackApiError(
            f"mcprack API HTTP {exc.code} for {client}: {detail}",
            status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise McprackApiError(f"mcprack API unreachable at {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise McprackApiError(f"mcprack API returned invalid JSON: {exc}") from exc

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

# mcprack-client

Shared Python library for **mcprack** MCP client configuration sync tools.

Used by:

- [`mcprack-sync-claude`](https://github.com/VitexSoftware/mcprack-sync-claude) — Claude Desktop / Claude Code
- [`mcprack-sync-cursor`](https://github.com/VitexSoftware/mcprack-sync-cursor) — Cursor IDE
- [`mcprack-sync-vscode`](https://github.com/VitexSoftware/mcprack-sync-vscode) — VS Code Copilot

## What it does

- Loads `MCPRACK_URL` + `MCPRACK_TOKEN` from process env, `~/.config/mcprack/client.env`, or `/etc/mcprack/client.env`
- Fetches `/api/v1/me/config/<client>` from a mcprack instance
- Merges the remote server map into an existing local JSON config while preserving unrelated keys and local-only servers
- Tracks previously managed server names under `~/.local/state/mcprack-sync/`

Stdlib only — no third-party Python dependencies.

## Settings file

```bash
# ~/.config/mcprack/client.env
MCPRACK_URL=https://mcprack.example.com
MCPRACK_TOKEN=mcr_...
```

Create a personal API token in the mcprack web UI (user menu → API tokens).

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]' 2>/dev/null || pip install -e .
pip install pytest
pytest
```

## License

MIT

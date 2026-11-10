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
`mcprack-sync-* configure --url … --token-file FILE` (or the hidden prompt) stores
it without putting it on the command line, where `ps` would show it.

## What is accepted from the server, and what is not

The sync tools write mcprack's answer into your own client configuration
(`~/.claude.json`, Cursor's and VS Code's `mcp.json`). In those files an entry
with `command`/`args` is a **program the client will run** — so a compromised or
tampered-with answer would otherwise run code on every machine that syncs. The
client therefore accepts only what mcprack really sends and refuses the **whole**
answer (exit status 3, nothing written) if anything is off:

- entries have only `type` (`http`/`sse`), `url` and `headers` — never
  `command`, `args`, `env`, `cwd` …;
- every `url` is on the **same origin** as `MCPRACK_URL` (scheme, host, port).
  If mcprack builds its URLs from a different `PUBLIC_BASE_URL`, list it:
  `MCPRACK_TRUSTED_ORIGINS=https://mcprack.example.com` (comma separated; or
  `configure --trusted-origin URL`);
- no `${VAR}` / `${env:VAR}` reference in a `url` or header: Claude Code, Cursor
  and VS Code substitute those from *your* environment, so text from the server
  could otherwise read it (`X-Leak: ${AWS_SECRET_ACCESS_KEY}`). The single
  exception is `Authorization: Bearer ${MCPRACK_TOKEN}` — your own token for
  that same server. Header names must be plain RFC 7230 tokens;
- the API token is only sent over **https** (or to loopback). Plain `http://` on
  a trusted private network needs `MCPRACK_ALLOW_INSECURE=1`
  (`configure --allow-insecure`);
- redirects are never followed (the token must not leave the configured host);
  the answer is size-limited; server text is stripped of control characters
  before it is printed.

Writing is careful as well: the `.bak` copy is created `0600` (it contains
everything the original does, e.g. OAuth tokens), a symlinked config stays a
symlink, the file's permissions are kept, an unchanged answer does not touch the
file at all, and if the client saved the file while we were merging, the merge is
redone on top of its newer content instead of overwriting it.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]' 2>/dev/null || pip install -e .
pip install pytest
pytest
```

## License

MIT

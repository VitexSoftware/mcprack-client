from __future__ import annotations

import json
from pathlib import Path

from mcprack_client.config import load_settings, save_settings
from mcprack_client.merge import merge_mcp_config
from mcprack_client.write import atomic_write_json, load_json_file


def test_merge_upserts_and_preserves_local():
    existing = {
        "mcpServers": {
            "local-only": {"command": "/bin/true"},
            "zabbix": {"command": "/old"},
        },
        "preferences": {"theme": "dark"},
    }
    remote = {
        "mcpServers": {
            "zabbix": {"type": "http", "url": "https://example/mcp"},
            "redmine": {"type": "http", "url": "https://redmine/mcp"},
        }
    }
    result = merge_mcp_config(
        existing,
        remote,
        servers_key="mcpServers",
        previously_managed=["zabbix"],
    )
    assert result.added == ["redmine"]
    assert result.updated == ["zabbix"]
    assert result.removed == []
    assert result.preserved == ["local-only"]
    assert result.config["preferences"] == {"theme": "dark"}
    assert result.config["mcpServers"]["local-only"]["command"] == "/bin/true"
    assert result.config["mcpServers"]["zabbix"]["url"] == "https://example/mcp"
    assert result.managed_names == ["redmine", "zabbix"]


def test_merge_removes_stale_managed():
    existing = {"servers": {"a": {"url": "1"}, "b": {"url": "2"}, "mine": {"url": "x"}}}
    remote = {"servers": {"a": {"url": "1b"}}}
    result = merge_mcp_config(
        existing,
        remote,
        servers_key="servers",
        previously_managed=["a", "b"],
    )
    assert result.removed == ["b"]
    assert "b" not in result.config["servers"]
    assert "mine" in result.config["servers"]
    assert result.updated == ["a"]


def test_merge_replace_all():
    existing = {"servers": {"mine": {"url": "x"}, "old": {"url": "y"}}}
    remote = {"servers": {"a": {"url": "1"}}}
    result = merge_mcp_config(
        existing,
        remote,
        servers_key="servers",
        previously_managed=["old"],
        replace_all=True,
    )
    assert result.config["servers"] == {"a": {"url": "1"}}
    assert result.preserved == []


def test_settings_precedence(tmp_path: Path):
    system = tmp_path / "system.env"
    user = tmp_path / "user.env"
    system.write_text("MCPRACK_URL=http://system\nMCPRACK_TOKEN=sys\n", encoding="utf-8")
    user.write_text("MCPRACK_URL=http://user\n", encoding="utf-8")
    settings = load_settings(
        env={"MCPRACK_TOKEN": "from-env"},
        user_path=user,
        system_path=system,
    )
    assert settings.url == "http://user"
    assert settings.token == "from-env"
    assert settings.ok()


def test_save_and_atomic_write(tmp_path: Path):
    cfg = save_settings("https://mcprack.example", "tok", path=tmp_path / "client.env")
    assert "MCPRACK_URL=https://mcprack.example" in cfg.read_text(encoding="utf-8")

    target = tmp_path / "mcp.json"
    atomic_write_json(target, {"servers": {"a": {"url": "1"}}})
    assert load_json_file(target)["servers"]["a"]["url"] == "1"
    atomic_write_json(target, {"servers": {"a": {"url": "2"}}})
    assert (tmp_path / "mcp.json.bak").is_file()
    assert json.loads((tmp_path / "mcp.json.bak").read_text(encoding="utf-8"))["servers"]["a"]["url"] == "1"

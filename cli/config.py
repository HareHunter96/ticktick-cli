"""Config and local persistence helpers for the TickTick CLI."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any

from .constants import CONFIG_ENV, DEFAULT_REDIRECT_URI, MCP_URL
from .errors import TickTickError


@dataclass
class Config:
    redirect_uri: str = DEFAULT_REDIRECT_URI
    mcp_url: str = MCP_URL
    mcp_client_id: str | None = None
    mcp_client_secret: str | None = None
    mcp_access_token: str | None = None
    mcp_token_expires_at: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return cls(
            redirect_uri=data.get("redirect_uri") or DEFAULT_REDIRECT_URI,
            mcp_url=data.get("mcp_url") or MCP_URL,
            mcp_client_id=data.get("mcp_client_id"),
            mcp_client_secret=data.get("mcp_client_secret"),
            mcp_access_token=data.get("mcp_access_token"),
            mcp_token_expires_at=data.get("mcp_token_expires_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "redirect_uri": self.redirect_uri,
            "mcp_url": self.mcp_url,
            "mcp_client_id": self.mcp_client_id,
            "mcp_client_secret": self.mcp_client_secret,
            "mcp_access_token": self.mcp_access_token,
            "mcp_token_expires_at": self.mcp_token_expires_at,
        }


def default_config_path() -> Path:
    if env_path := os.environ.get(CONFIG_ENV):
        return Path(env_path).expanduser()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return config_home / "ticktick-cli" / "config.json"


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        return Config.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise TickTickError(f"Invalid config JSON at {path}: {exc}") from exc


def save_config(path: Path, config: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
        path.parent.chmod(0o700)
    except OSError:
        pass


def first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def prompt_client_secret(show_input: bool) -> str:
    if show_input:
        return input("TickTick client secret (visible): ").strip()
    print("TickTick client secret input is hidden. Type or paste it, then press Enter.", file=sys.stderr)
    return getpass("TickTick client secret: ").strip()

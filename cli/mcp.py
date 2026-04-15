"""Minimal MCP-over-HTTP client helpers for the TickTick CLI."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from .config import Config
from .constants import DEFAULT_TIMEOUT
from .errors import TickTickError

MCP_PROTOCOL_VERSION = "2025-03-26"
CLIENT_INFO = {"name": "ticktick-cli", "version": "0.1.0"}


def http_json_response(request: urllib.request.Request) -> tuple[Any, dict[str, str]]:
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            body = response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise TickTickError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise TickTickError(f"Network error: {exc.reason}") from exc

    if not body:
        return None, headers
    try:
        return json.loads(body.decode("utf-8")), headers
    except json.JSONDecodeError as exc:
        raise TickTickError(f"Invalid JSON response: {body[:200]!r}") from exc


def config_access_token(config: Config) -> str:
    token = (config.mcp_access_token or "").strip()
    if not token:
        raise TickTickError("MCP access token is missing. Run `ticktick auth` first.")
    if config.mcp_token_expires_at is not None and time.time() >= config.mcp_token_expires_at:
        raise TickTickError("MCP access token has expired. Run `ticktick auth` again.")
    return token


def rpc_headers(token: str, *, session_id: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return headers


def rpc_request(
    url: str,
    token: str,
    method: str,
    *,
    params: dict[str, Any] | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
) -> tuple[Any, dict[str, str]]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    if request_id is not None:
        payload["id"] = request_id

    request = urllib.request.Request(
        url.rstrip("/"),
        data=json.dumps(payload).encode("utf-8"),
        headers=rpc_headers(token, session_id=session_id),
        method="POST",
    )
    return http_json_response(request)


def extract_rpc_result(response: Any, method: str) -> Any:
    if not isinstance(response, dict):
        raise TickTickError(f"Unexpected MCP response for {method}: {response!r}")
    if "error" in response:
        error = response["error"]
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message") or error
            prefix = f"MCP {method} failed"
            if code is not None:
                prefix += f" ({code})"
            raise TickTickError(f"{prefix}: {message}")
        raise TickTickError(f"MCP {method} failed: {error!r}")
    if "result" not in response:
        raise TickTickError(f"Unexpected MCP response for {method}: {response!r}")
    return response["result"]


def initialize_session(url: str, token: str) -> str | None:
    response, headers = rpc_request(
        url,
        token,
        "initialize",
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        },
        request_id="ticktick-cli-init",
    )
    extract_rpc_result(response, "initialize")
    session_id = headers.get("mcp-session-id")

    rpc_request(
        url,
        token,
        "notifications/initialized",
        params={},
        session_id=session_id,
    )
    return session_id


def call_mcp_tool(config: Config, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    token = config_access_token(config)
    session_id = initialize_session(config.mcp_url, token)
    response, _headers = rpc_request(
        config.mcp_url,
        token,
        "tools/call",
        params={"name": tool_name, "arguments": arguments or {}},
        request_id=f"ticktick-cli-{tool_name}",
        session_id=session_id,
    )
    return extract_rpc_result(response, "tools/call")

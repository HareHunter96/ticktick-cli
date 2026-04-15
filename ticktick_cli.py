#!/usr/bin/env python3
"""Thin entrypoint and compatibility exports for the TickTick CLI."""

from cli.auth import (
    basic_auth_value,
    build_authorize_url,
    command_auth,
    exchange_code_for_mcp_token,
    extract_oauth_code,
    http_json,
    mcp_registration_payload,
    pkce_challenge,
    pkce_verifier,
    register_mcp_client,
)
from cli.config import (
    Config,
    default_config_path,
    first_non_empty,
    load_config,
    prompt_client_secret,
    save_config,
)
from cli.errors import TickTickError
from cli.mcp import call_mcp_tool, config_access_token, initialize_session
from cli.parser import build_parser, main
from cli.tool_commands import command_mcp_tool, extract_mcp_payload, print_mcp_payload


if __name__ == "__main__":
    raise SystemExit(main())

"""OAuth and auth command implementation for the TickTick CLI."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import first_non_empty, load_config, prompt_client_secret, save_config
from .config import Config
from .constants import (
    AUTHORIZE_URL,
    CLIENT_ID_ENV,
    CLIENT_SECRET_ENV,
    DEFAULT_SCOPE,
    DEFAULT_TIMEOUT,
    MCP_URL,
    REGISTER_URL,
    TOKEN_URL,
)
from .errors import TickTickError


def extract_oauth_code(value: str, expected_state: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise TickTickError("OAuth code is required.")

    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme or parsed.netloc or parsed.query:
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if not code:
            raise TickTickError("Redirect URL does not contain an OAuth code.")
        state = params.get("state", [None])[0]
        if state is not None and state != expected_state:
            raise TickTickError("OAuth state mismatch.")
        return code

    return candidate


def build_authorize_url(
    client_id: str,
    state: str,
    *,
    redirect_uri: str | None = None,
    resource: str | None = None,
    code_challenge: str | None = None,
) -> str:
    params = {
        "client_id": client_id,
        "scope": DEFAULT_SCOPE,
        "state": state,
        "response_type": "code",
    }
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    if resource:
        params["resource"] = resource
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def basic_auth_value(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def mcp_registration_payload(redirect_uri: str) -> dict[str, Any]:
    return {
        "application_type": "native",
        "client_name": "ticktick-cli",
        "grant_types": ["authorization_code"],
        "redirect_uris": [redirect_uri],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


def http_json(request: urllib.request.Request) -> Any:
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise TickTickError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise TickTickError(f"Network error: {exc.reason}") from exc
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TickTickError(f"Invalid JSON response: {body[:200]!r}") from exc


def register_mcp_client(redirect_uri: str) -> dict[str, Any]:
    request = urllib.request.Request(
        REGISTER_URL,
        data=json.dumps(mcp_registration_payload(redirect_uri)).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    registration = http_json(request)
    if not isinstance(registration, dict) or not registration.get("client_id"):
        raise TickTickError(f"Unexpected MCP client registration response: {registration!r}")
    return registration


def exchange_code_for_mcp_token(
    client_id: str,
    client_secret: str | None,
    redirect_uri: str,
    code: str,
    code_verifier: str,
    resource: str,
) -> dict[str, Any]:
    params = {
        "code": code,
        "grant_type": "authorization_code",
        "scope": DEFAULT_SCOPE,
        "redirect_uri": redirect_uri,
        "resource": resource,
        "code_verifier": code_verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    if client_secret:
        headers["Authorization"] = basic_auth_value(client_id, client_secret)
    else:
        params["client_id"] = client_id

    request = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(params).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        return http_json(request)
    except TickTickError as first_error:
        if not client_secret:
            raise
        fallback = dict(params)
        fallback["client_id"] = client_id
        fallback["client_secret"] = client_secret
        fallback_request = urllib.request.Request(
            TOKEN_URL,
            data=urllib.parse.urlencode(fallback).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        try:
            return http_json(fallback_request)
        except TickTickError:
            raise first_error


def command_auth(args: argparse.Namespace, config_path) -> int:
    config = load_config(config_path)
    redirect_uri = args.redirect_uri or config.redirect_uri
    mcp_url = args.url or config.mcp_url or MCP_URL
    resource = args.resource or mcp_url
    client_id = first_non_empty(args.client_id, os.environ.get(CLIENT_ID_ENV), config.mcp_client_id)
    client_secret = first_non_empty(args.client_secret, os.environ.get(CLIENT_SECRET_ENV), config.mcp_client_secret)

    if not client_id:
        registration = register_mcp_client(redirect_uri)
        client_id = registration["client_id"]
        client_secret = registration.get("client_secret")
    elif not client_secret and not args.public_client:
        client_secret = prompt_client_secret(args.show_secret_input)

    state = secrets.token_urlsafe(24)
    verifier = pkce_verifier()
    url = build_authorize_url(
        client_id,
        state,
        redirect_uri=redirect_uri,
        resource=resource,
        code_challenge=pkce_challenge(verifier),
    )
    print(url, file=sys.stderr)
    pasted = input("Paste redirected URL or code: ")
    code = extract_oauth_code(pasted, state)
    token = exchange_code_for_mcp_token(client_id, client_secret, redirect_uri, code, verifier, resource)

    config.redirect_uri = redirect_uri
    config.mcp_url = mcp_url
    config.mcp_client_id = client_id
    config.mcp_client_secret = client_secret
    config.mcp_access_token = token["access_token"]
    config.mcp_token_expires_at = int(time.time()) + int(token.get("expires_in", 0)) - 60
    save_config(config_path, config)
    print(f"saved\tmcp\t{config_path}")
    return 0

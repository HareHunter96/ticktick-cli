"""Helpers for implementing MCP-backed CLI commands."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .config import Config
from .constants import REPEATABLE_FLAG_OVERRIDES
from .mcp import call_mcp_tool
from .metadata import normalize_schema


def extract_mcp_payload(result: Any) -> Any:
    if not isinstance(result, dict):
        return result

    structured = result.get("structuredContent")
    if structured is not None:
        return structured

    content = result.get("content")
    if not isinstance(content, list):
        return result

    text_chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            text_chunks.append(text.strip())

    if not text_chunks:
        return result
    if len(text_chunks) == 1:
        return text_chunks[0]
    return "\n".join(text_chunks)


def print_mcp_payload(result: Any) -> None:
    payload = extract_mcp_payload(result)
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def coerce_cli_value(value: Any, schema: dict[str, Any]) -> Any:
    normalized = normalize_schema(schema)
    if value is None:
        return None
    if normalized.get("type") == "boolean" and isinstance(value, str):
        return value == "true"
    if normalized.get("type") == "json" and isinstance(value, str):
        return json.loads(value)
    if normalized.get("type") == "array" and "$ref" in normalized.get("items", {}) and isinstance(value, str):
        return json.loads(value)
    return value


def namespace_to_arguments(args: argparse.Namespace, input_schema: dict[str, Any]) -> dict[str, Any]:
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    raw = vars(args)
    arguments: dict[str, Any] = {}

    for name, schema in properties.items():
        raw_name = name if name in raw else REPEATABLE_FLAG_OVERRIDES.get(name, name)
        if raw_name not in raw or raw[raw_name] is None or not isinstance(schema, dict):
            continue
        arguments[name] = coerce_cli_value(raw[raw_name], schema)

    return arguments


def command_mcp_tool(args: argparse.Namespace, config: Config) -> int:
    arguments = namespace_to_arguments(args, getattr(args, "mcp_input_schema", {}))
    result = call_mcp_tool(config, args.mcp_tool_name, arguments)
    print_mcp_payload(result)
    return 0

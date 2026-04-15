"""Argument parser construction and command routing for the TickTick CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .auth import command_auth
from .config import default_config_path, load_config
from .constants import MCP_URL, NAMESPACE_HELP, REPEATABLE_FLAG_OVERRIDES
from .errors import TickTickError
from .metadata import CliCommandSpec, load_cli_command_specs, normalize_schema
from .tool_commands import command_mcp_tool


def property_to_flag_name(name: str, schema: dict[str, Any]) -> str:
    schema_type = normalize_schema(schema).get("type")
    if schema_type == "array":
        return REPEATABLE_FLAG_OVERRIDES.get(name, name)
    return name


def argument_help(_name: str, schema: dict[str, Any]) -> str | None:
    normalized = normalize_schema(schema)
    label = normalized.get("description") or normalized.get("title")
    if not label:
        return None
    if normalized.get("type") == "json":
        return f"{label} (JSON)"
    if normalized.get("type") == "array" and "$ref" in normalized.get("items", {}):
        return f"{label} (JSON)"
    return str(label)


def add_schema_argument(parser: argparse.ArgumentParser, name: str, schema: dict[str, Any], required: bool) -> None:
    normalized = normalize_schema(schema)
    flag_name = property_to_flag_name(name, schema).replace("_", "-")
    kwargs: dict[str, Any] = {"required": required}
    help_text = argument_help(name, schema)
    if help_text:
        kwargs["help"] = help_text

    if normalized.get("type") == "json":
        kwargs["metavar"] = "JSON"
        parser.add_argument(f"--{flag_name}", **kwargs)
        return

    if normalized.get("type") == "array":
        items = normalized.get("items", {})
        if "$ref" in items:
            kwargs["metavar"] = "JSON"
            parser.add_argument(f"--{flag_name}", **kwargs)
            return
        item_type = items.get("type")
        kwargs["action"] = "append"
        if item_type == "integer":
            kwargs["type"] = int
        parser.add_argument(f"--{flag_name}", **kwargs)
        return

    if normalized.get("type") == "boolean":
        kwargs["choices"] = ["true", "false"]
        parser.add_argument(f"--{flag_name}", **kwargs)
        return

    if "enum" in normalized:
        kwargs["choices"] = normalized["enum"]

    if normalized.get("type") == "integer":
        kwargs["type"] = int

    parser.add_argument(f"--{flag_name}", **kwargs)


def add_mcp_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    spec: CliCommandSpec,
    leaf_name: str,
) -> None:
    parser = subparsers.add_parser(leaf_name, help=spec.summary, description=spec.summary)
    input_schema = spec.input_schema if isinstance(spec.input_schema, dict) else {}
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            continue
        add_schema_argument(parser, name, schema, required=name in required)
    parser.set_defaults(handler=command_mcp_tool, mcp_tool_name=spec.tool_name, mcp_input_schema=input_schema)


def add_auth_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    auth = subparsers.add_parser("auth", help="Authenticate for TickTick MCP", description="Authenticate for TickTick MCP")
    auth.add_argument("--client-id")
    auth.add_argument("--client-secret")
    auth.add_argument("--redirect-uri", default=None)
    auth.add_argument("--url", default=None, help=f"MCP server URL; default {MCP_URL}")
    auth.add_argument("--resource", default=None, help="OAuth resource indicator; defaults to the MCP URL")
    auth.add_argument("--public-client", action="store_true", help="Do not send a client secret")
    auth.add_argument(
        "--show-secret-input",
        action="store_true",
        help="Show client secret while typing. Use only if hidden input does not work in your terminal.",
    )
    auth.set_defaults(handler=command_auth, needs_config=False)


def add_preference_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    specs: list[CliCommandSpec],
) -> None:
    spec = next((item for item in specs if item.path == ("preference",)), None)
    if spec is None:
        return
    preference = subparsers.add_parser("preference", help=spec.summary, description=spec.summary)
    input_schema = spec.input_schema if isinstance(spec.input_schema, dict) else {}
    preference.set_defaults(handler=command_mcp_tool, mcp_tool_name=spec.tool_name, mcp_input_schema=input_schema)


def add_namespace_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    specs: list[CliCommandSpec],
) -> None:
    for namespace in ("project", "task", "habit", "focus"):
        namespace_parser = subparsers.add_parser(
            namespace,
            help=NAMESPACE_HELP[namespace],
            description=NAMESPACE_HELP[namespace],
        )
        namespace_subparsers = namespace_parser.add_subparsers(dest=f"{namespace}_command", required=True)
        for spec in specs:
            if spec.path[0] != namespace:
                continue
            add_mcp_command(namespace_subparsers, spec, spec.path[1])


def build_parser() -> argparse.ArgumentParser:
    specs = load_cli_command_specs()
    parser = argparse.ArgumentParser(prog="ticktick", description="TickTick MCP CLI")
    parser.add_argument("--config", type=Path, default=default_config_path(), help="Config JSON path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_auth_parser(subparsers)
    add_preference_parser(subparsers, specs)
    add_namespace_parsers(subparsers, specs)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = args.config.expanduser()
    try:
        if getattr(args, "needs_config", True):
            config = load_config(config_path)
            return args.handler(args, config)
        return args.handler(args, config_path)
    except TickTickError as exc:
        print(f"ticktick: {exc}", file=sys.stderr)
        return 1

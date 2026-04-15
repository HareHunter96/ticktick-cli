"""Metadata layer for MCP-derived CLI command generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CliCommandSpec:
    path: tuple[str, ...]
    tool_name: str
    summary: str
    input_schema: dict[str, Any]


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        return {
            "type": "json",
            "$ref": schema["$ref"],
            "title": schema.get("title"),
            "description": schema.get("description"),
        }
    if "anyOf" in schema:
        non_null = [option for option in schema["anyOf"] if option.get("type") != "null"]
        if len(non_null) == 1:
            merged = dict(schema)
            merged.pop("anyOf", None)
            merged.update(non_null[0])
            return merged
    return schema


CLI_TREE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("preference",), "get_user_preference"),
    (("project", "list"), "list_projects"),
    (("project", "get"), "get_project_by_id"),
    (("project", "with-undone"), "get_project_with_undone_tasks"),
    (("project", "create"), "create_project"),
    (("project", "update"), "update_project"),
    (("task", "create"), "create_task"),
    (("task", "update"), "update_task"),
    (("task", "get"), "get_task_by_id"),
    (("task", "get-in-project"), "get_task_in_project"),
    (("task", "complete"), "complete_task"),
    (("task", "complete-many-in-project"), "complete_tasks_in_project"),
    (("task", "search"), "search"),
    (("task", "search-task"), "search_task"),
    (("task", "fetch"), "fetch"),
    (("task", "undone-by-date"), "list_undone_tasks_by_date"),
    (("task", "undone-by-time-query"), "list_undone_tasks_by_time_query"),
    (("task", "filter"), "filter_tasks"),
    (("task", "completed-by-date"), "list_completed_tasks_by_date"),
    (("task", "move"), "move_task"),
    (("task", "batch-add"), "batch_add_tasks"),
    (("task", "batch-update"), "batch_update_tasks"),
    (("habit", "list"), "list_habits"),
    (("habit", "list-sections"), "list_habit_sections"),
    (("habit", "get"), "get_habit"),
    (("habit", "create"), "create_habit"),
    (("habit", "update"), "update_habit"),
    (("habit", "get-checkins"), "get_habit_checkins"),
    (("habit", "upsert-checkins"), "upsert_habit_checkins"),
    (("focus", "get"), "get_focus"),
    (("focus", "list-by-time"), "get_focuses_by_time"),
    (("focus", "delete"), "delete_focus"),
)


def default_mcp_tools_path() -> Traversable:
    return resources.files("cli").joinpath("mcp-tools.json")


def load_mcp_tools_index(path: Path | Traversable | None = None) -> dict[str, dict[str, Any]]:
    tools_path = path or default_mcp_tools_path()
    data = json.loads(tools_path.read_text(encoding="utf-8"))
    tools = data.get("tools", []) if isinstance(data, dict) else data
    if not isinstance(tools, list):
        raise ValueError(f"Invalid MCP tools payload in {tools_path}")
    return {tool["name"]: tool for tool in tools if isinstance(tool, dict) and tool.get("name")}


def summarize_description(description: str) -> str:
    first_line = description.strip().splitlines()[0].strip() if description.strip() else ""
    if not first_line:
        return ""
    sentence, dot, _rest = first_line.partition(". ")
    return sentence + ("." if dot else "")


def load_cli_command_specs(path: Path | Traversable | None = None) -> list[CliCommandSpec]:
    tools = load_mcp_tools_index(path)
    specs: list[CliCommandSpec] = []
    for cli_path, tool_name in CLI_TREE:
        tool = tools.get(tool_name)
        if tool is None:
            raise ValueError(f"Missing MCP tool in spec: {tool_name}")
        specs.append(
            CliCommandSpec(
                path=cli_path,
                tool_name=tool_name,
                summary=summarize_description(str(tool.get("description") or "")),
                input_schema=tool.get("inputSchema", {}),
            )
        )
    return specs

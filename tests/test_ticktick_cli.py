import contextlib
import io
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import ticktick_cli
from cli import metadata


class TickTickCliTests(unittest.TestCase):
    def test_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = ticktick_cli.Config(
                redirect_uri="http://127.0.0.1:8080/",
                mcp_url="https://mcp.ticktick.com/",
                mcp_client_id="client",
                mcp_client_secret="secret",
                mcp_access_token="token",
                mcp_token_expires_at=123,
            )

            ticktick_cli.save_config(path, config)

            self.assertEqual(ticktick_cli.load_config(path), config)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["mcp_client_id"], "client")
            self.assertNotIn("client_id", saved)

    def test_first_non_empty_strips_and_skips_blank_values(self) -> None:
        self.assertEqual(ticktick_cli.first_non_empty(None, "", "  value  "), "value")
        self.assertIsNone(ticktick_cli.first_non_empty(None, "   ", ""))

    def test_mcp_authorize_url_includes_resource_and_pkce(self) -> None:
        url = ticktick_cli.build_authorize_url(
            "id",
            "state",
            redirect_uri="http://127.0.0.1:8080/",
            resource="https://mcp.ticktick.com/",
            code_challenge="challenge",
        )

        params = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))

        self.assertEqual(urllib.parse.unquote(params["resource"]), "https://mcp.ticktick.com/")
        self.assertEqual(params["code_challenge"], "challenge")
        self.assertEqual(params["code_challenge_method"], "S256")

    def test_mcp_registration_payload_uses_public_native_client(self) -> None:
        payload = ticktick_cli.mcp_registration_payload("http://127.0.0.1:8080/")

        self.assertEqual(payload["application_type"], "native")
        self.assertEqual(payload["client_name"], "ticktick-cli")
        self.assertEqual(payload["token_endpoint_auth_method"], "none")
        self.assertEqual(payload["redirect_uris"], ["http://127.0.0.1:8080/"])

    def test_extract_oauth_code_from_redirect_url_with_matching_state(self) -> None:
        self.assertEqual(
            ticktick_cli.extract_oauth_code("http://127.0.0.1:8080/?code=abc123&state=ok", "ok"),
            "abc123",
        )

    def test_extract_oauth_code_rejects_mismatched_state(self) -> None:
        with self.assertRaises(ticktick_cli.TickTickError):
            ticktick_cli.extract_oauth_code("http://127.0.0.1:8080/?code=abc123&state=bad", "ok")

    def test_extract_oauth_code_accepts_raw_code(self) -> None:
        self.assertEqual(ticktick_cli.extract_oauth_code(" raw-code ", "ok"), "raw-code")

    def test_extract_oauth_code_rejects_url_without_code(self) -> None:
        with self.assertRaises(ticktick_cli.TickTickError):
            ticktick_cli.extract_oauth_code("http://127.0.0.1:8080/?state=ok", "ok")

    def test_cli_metadata_loads_all_planned_commands(self) -> None:
        specs = metadata.load_cli_command_specs()

        self.assertEqual(len(specs), len(metadata.CLI_TREE))
        self.assertIn(("task", "create"), [spec.path for spec in specs])
        self.assertIn(("preference",), [spec.path for spec in specs])

    def test_cli_metadata_uses_packaged_mcp_tools_resource(self) -> None:
        tools_path = metadata.default_mcp_tools_path()
        self.assertEqual(tools_path.name, "mcp-tools.json")
        self.assertIn('"name": "get_user_preference"', tools_path.read_text(encoding="utf-8"))

    def test_root_help_contains_expected_top_level_namespaces(self) -> None:
        help_text = ticktick_cli.build_parser().format_help()

        for namespace in ("auth", "preference", "project", "task", "habit", "focus"):
            self.assertIn(namespace, help_text)
        self.assertNotIn("projects", help_text)
        self.assertNotIn("tasks", help_text)
        self.assertNotIn("mcp", help_text)

    def test_auth_parser_accepts_mcp_flags(self) -> None:
        args = ticktick_cli.build_parser().parse_args([
            "auth",
            "--client-id",
            "id",
            "--client-secret",
            "secret",
            "--redirect-uri",
            "http://127.0.0.1:8080/",
            "--url",
            "https://mcp.ticktick.com/",
            "--resource",
            "https://mcp.ticktick.com/",
            "--public-client",
            "--show-secret-input",
        ])

        self.assertEqual(args.command, "auth")
        self.assertEqual(args.client_id, "id")
        self.assertEqual(args.client_secret, "secret")
        self.assertTrue(args.public_client)
        self.assertTrue(args.show_secret_input)

    def test_auth_help_does_not_list_preference_subcommand(self) -> None:
        parser = ticktick_cli.build_parser()
        auth_parser = parser._subparsers._group_actions[0].choices["auth"]
        help_text = auth_parser.format_help()

        self.assertNotIn("preference", help_text)
        self.assertIn("--client-id", help_text)

    def test_preference_help_is_top_level(self) -> None:
        parser = ticktick_cli.build_parser()
        preference_parser = parser._subparsers._group_actions[0].choices["preference"]
        help_text = preference_parser.format_help()

        self.assertIn("Get user preferences including timezone settings.", help_text)

    def test_namespace_help_lists_leaf_commands(self) -> None:
        parser = ticktick_cli.build_parser()
        task_parser = parser._subparsers._group_actions[0].choices["task"]
        help_text = task_parser.format_help()

        for leaf in ("create", "get", "filter", "batch-add", "batch-update"):
            self.assertIn(leaf, help_text)

    def test_project_update_help_shows_nullable_boolean_flag(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            ticktick_cli.build_parser().parse_args(["project", "update", "--help"])

        help_text = out.getvalue()
        self.assertIn("--closed {true,false}", help_text)
        self.assertIn("--project-id PROJECT_ID", help_text)

    def test_task_create_help_shows_json_argument(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            ticktick_cli.build_parser().parse_args(["task", "create", "--help"])

        self.assertIn("--task JSON", out.getvalue())

    def test_task_complete_many_accepts_repeatable_task_id(self) -> None:
        args = ticktick_cli.build_parser().parse_args([
            "task",
            "complete-many-in-project",
            "--project-id",
            "p1",
            "--task-id",
            "t1",
            "--task-id",
            "t2",
        ])

        self.assertEqual(args.project_id, "p1")
        self.assertEqual(args.task_id, ["t1", "t2"])

    def test_task_undone_by_time_query_help_shows_enum_choices(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            ticktick_cli.build_parser().parse_args(["task", "undone-by-time-query", "--help"])

        help_text = out.getvalue()
        self.assertIn("today", help_text)
        self.assertIn("next7day", help_text)

    def test_habit_get_checkins_accepts_repeatable_habit_id(self) -> None:
        args = ticktick_cli.build_parser().parse_args([
            "habit",
            "get-checkins",
            "--habit-id",
            "h1",
            "--habit-id",
            "h2",
            "--from-stamp",
            "20260401",
            "--to-stamp",
            "20260430",
        ])

        self.assertEqual(args.habit_id, ["h1", "h2"])
        self.assertEqual(args.from_stamp, 20260401)
        self.assertEqual(args.to_stamp, 20260430)

    def test_preference_requires_saved_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = ticktick_cli.main(["--config", str(path), "preference"])

        self.assertEqual(result, 1)
        self.assertIn("MCP access token is missing", stderr.getvalue())

    def test_preference_command_prints_pretty_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"content": [{"type": "text", "text": "{\n  \"time_zone\": \"Europe/Kiev\"\n}"}]},
                ),
            ):
                result = ticktick_cli.main(["--config", str(path), "preference"])

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {"time_zone": "Europe/Kiev"})

    def test_project_list_command_calls_mcp_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "p1", "name": "Inbox"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "project", "list"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "list_projects", {})
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "p1", "name": "Inbox"}]})

    def test_project_get_command_passes_project_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "p1", "name": "Inbox"}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "project", "get", "--project-id", "p1"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "get_project_by_id", {"project_id": "p1"})
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "p1", "name": "Inbox"})

    def test_project_with_undone_command_passes_project_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"project": {"id": "p1"}, "tasks": []}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "project", "with-undone", "--project-id", "p1"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "get_project_with_undone_tasks", {"project_id": "p1"})
        self.assertEqual(json.loads(stdout.getvalue()), {"project": {"id": "p1"}, "tasks": []})

    def test_project_create_command_passes_optional_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "p1", "name": "New Project"}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "project",
                        "create",
                        "--name",
                        "New Project",
                        "--color",
                        "#123456",
                        "--kind",
                        "TASK",
                        "--sort-order",
                        "7",
                        "--view-mode",
                        "kanban",
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "create_project",
            {"name": "New Project", "color": "#123456", "kind": "TASK", "sort_order": 7, "view_mode": "kanban"},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "p1", "name": "New Project"})

    def test_project_update_command_coerces_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "p1", "closed": True}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "project",
                        "update",
                        "--project-id",
                        "p1",
                        "--closed",
                        "true",
                        "--sort-order",
                        "11",
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "update_project",
            {"project_id": "p1", "closed": True, "sort_order": 11},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "p1", "closed": True})

    def test_task_create_command_passes_json_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "t1", "title": "Buy milk"}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "create",
                        "--task",
                        '{"title":"Buy milk","projectId":"p1","priority":3}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "create_task",
            {"task": {"title": "Buy milk", "projectId": "p1", "priority": 3}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "t1", "title": "Buy milk"})

    def test_task_update_command_passes_task_id_and_json_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "t1", "title": "Buy oat milk", "priority": 5}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "update",
                        "--task-id",
                        "t1",
                        "--task",
                        '{"title":"Buy oat milk","priority":5}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "update_task",
            {"task_id": "t1", "task": {"title": "Buy oat milk", "priority": 5}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "t1", "title": "Buy oat milk", "priority": 5})

    def test_task_get_command_passes_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "t1", "title": "Buy milk", "projectId": "p1"}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "task", "get", "--task-id", "t1"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "get_task_by_id", {"task_id": "t1"})
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "t1", "title": "Buy milk", "projectId": "p1"})

    def test_task_get_in_project_command_passes_project_id_and_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "t1", "title": "Buy milk", "projectId": "p1"}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    ["--config", str(path), "task", "get-in-project", "--project-id", "p1", "--task-id", "t1"]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "get_task_in_project", {"project_id": "p1", "task_id": "t1"})
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "t1", "title": "Buy milk", "projectId": "p1"})

    def test_task_complete_command_passes_project_id_and_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "t1", "status": 2}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    ["--config", str(path), "task", "complete", "--project-id", "p1", "--task-id", "t1"]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "complete_task", {"project_id": "p1", "task_id": "t1"})
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "t1", "status": 2})

    def test_task_complete_many_in_project_passes_repeatable_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"completedTaskIds": ["t1", "t2"], "failedTaskIds": []}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "complete-many-in-project",
                        "--project-id",
                        "p1",
                        "--task-id",
                        "t1",
                        "--task-id",
                        "t2",
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "complete_tasks_in_project",
            {"project_id": "p1", "task_ids": ["t1", "t2"]},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"completedTaskIds": ["t1", "t2"], "failedTaskIds": []})

    def test_task_search_command_passes_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "t1", "title": "invoice", "url": "https://ticktick.com"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "task", "search", "--query", "invoice"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "search", {"query": "invoice"})
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "t1", "title": "invoice", "url": "https://ticktick.com"}]})

    def test_task_search_task_command_passes_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"items": [{"id": "t1", "title": "invoice", "url": "https://ticktick.com"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "task", "search-task", "--query", "invoice"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "search_task", {"query": "invoice"})
        self.assertEqual(json.loads(stdout.getvalue()), {"items": [{"id": "t1", "title": "invoice", "url": "https://ticktick.com"}]})

    def test_task_fetch_command_passes_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={
                        "structuredContent": {
                            "id": "t1",
                            "title": "invoice",
                            "text": "Send PDF",
                            "url": "https://ticktick.com",
                            "metadata": {"priority": 3},
                        }
                    },
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "task", "fetch", "--id", "t1"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "fetch", {"id": "t1"})
        self.assertEqual(
            json.loads(stdout.getvalue()),
            {"id": "t1", "title": "invoice", "text": "Send PDF", "url": "https://ticktick.com", "metadata": {"priority": 3}},
        )

    def test_task_undone_by_date_command_passes_json_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "t1", "title": "Today task"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "undone-by-date",
                        "--search",
                        '{"startDate":"2026-04-15","endDate":"2026-04-16"}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "list_undone_tasks_by_date",
            {"search": {"startDate": "2026-04-15", "endDate": "2026-04-16"}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "t1", "title": "Today task"}]})

    def test_task_undone_by_time_query_command_passes_enum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "t1"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    ["--config", str(path), "task", "undone-by-time-query", "--query-command", "next7day"]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "list_undone_tasks_by_time_query",
            {"query_command": "next7day"},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "t1"}]})

    def test_task_filter_command_passes_json_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "t1", "projectId": "p1"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "filter",
                        "--filter",
                        '{"projectIds":["p1"],"status":0}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "filter_tasks",
            {"filter": {"projectIds": ["p1"], "status": 0}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "t1", "projectId": "p1"}]})

    def test_task_completed_by_date_command_passes_json_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "t1", "status": 2}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "completed-by-date",
                        "--search",
                        '{"from":"2026-04-01","to":"2026-04-15"}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "list_completed_tasks_by_date",
            {"search": {"from": "2026-04-01", "to": "2026-04-15"}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "t1", "status": 2}]})

    def test_task_move_command_passes_json_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id2error": {}, "id2etag": {"t1": "etag1"}}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "move",
                        "--moves",
                        '[{"fromProjectId":"p1","toProjectId":"p2","taskId":"t1"}]',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "move_task",
            {"moves": [{"fromProjectId": "p1", "toProjectId": "p2", "taskId": "t1"}]},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id2error": {}, "id2etag": {"t1": "etag1"}})

    def test_task_batch_add_command_passes_json_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id2error": {}, "id2etag": {"t1": "etag1"}}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "batch-add",
                        "--tasks",
                        '[{"title":"Task 1","projectId":"p1"},{"title":"Task 2","projectId":"p1"}]',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "batch_add_tasks",
            {"tasks": [{"title": "Task 1", "projectId": "p1"}, {"title": "Task 2", "projectId": "p1"}]},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id2error": {}, "id2etag": {"t1": "etag1"}})

    def test_task_batch_update_command_passes_json_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id2error": {}, "id2etag": {"t1": "etag2"}}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "task",
                        "batch-update",
                        "--tasks",
                        '[{"id":"t1","title":"Renamed","projectId":"p1"}]',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "batch_update_tasks",
            {"tasks": [{"id": "t1", "title": "Renamed", "projectId": "p1"}]},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id2error": {}, "id2etag": {"t1": "etag2"}})

    def test_habit_list_command_calls_mcp_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "h1", "name": "Workout"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "habit", "list"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "list_habits", {})
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "h1", "name": "Workout"}]})

    def test_habit_list_sections_command_calls_mcp_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "s1", "name": "Health"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "habit", "list-sections"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "list_habit_sections", {})
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "s1", "name": "Health"}]})

    def test_habit_get_command_passes_habit_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "h1", "name": "Workout"}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(["--config", str(path), "habit", "get", "--habit-id", "h1"])

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "get_habit", {"habit_id": "h1"})
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "h1", "name": "Workout"})

    def test_habit_create_command_passes_json_habit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "h1", "name": "Workout", "goal": 3}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "habit",
                        "create",
                        "--habit",
                        '{"name":"Workout","goal":3,"unit":"times"}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "create_habit",
            {"habit": {"name": "Workout", "goal": 3, "unit": "times"}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "h1", "name": "Workout", "goal": 3})

    def test_habit_update_command_passes_habit_id_and_json_habit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "h1", "name": "Morning workout", "goal": 4}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "habit",
                        "update",
                        "--habit-id",
                        "h1",
                        "--habit",
                        '{"name":"Morning workout","goal":4}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "update_habit",
            {"habit_id": "h1", "habit": {"name": "Morning workout", "goal": 4}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "h1", "name": "Morning workout", "goal": 4})

    def test_habit_get_checkins_command_passes_repeatable_habit_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"habitId": "h1"}, {"habitId": "h2"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "habit",
                        "get-checkins",
                        "--habit-id",
                        "h1",
                        "--habit-id",
                        "h2",
                        "--from-stamp",
                        "20260401",
                        "--to-stamp",
                        "20260430",
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "get_habit_checkins",
            {"habit_ids": ["h1", "h2"], "from_stamp": 20260401, "to_stamp": 20260430},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"habitId": "h1"}, {"habitId": "h2"}]})

    def test_habit_upsert_checkins_command_passes_habit_id_and_json_checkin_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"habitId": "h1", "checkins": [{"stamp": 20260415, "value": 1}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "habit",
                        "upsert-checkins",
                        "--habit-id",
                        "h1",
                        "--checkin-data",
                        '{"checkins":[{"stamp":20260415,"value":1}]}',
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "upsert_habit_checkins",
            {"habit_id": "h1", "checkin_data": {"checkins": [{"stamp": 20260415, "value": 1}]}},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"habitId": "h1", "checkins": [{"stamp": 20260415, "value": 1}]})

    def test_focus_get_command_passes_focus_id_and_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "f1", "type": 0, "duration": 1500}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    ["--config", str(path), "focus", "get", "--focus-id", "f1", "--type", "0"]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "get_focus", {"focus_id": "f1", "type": 0})
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "f1", "type": 0, "duration": 1500})

    def test_focus_list_by_time_command_passes_range_and_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"result": [{"id": "f1"}, {"id": "f2"}]}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    [
                        "--config",
                        str(path),
                        "focus",
                        "list-by-time",
                        "--from-time",
                        "2026-04-01T00:00:00Z",
                        "--to-time",
                        "2026-04-30T23:59:59Z",
                        "--type",
                        "1",
                    ]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(
            mock.ANY,
            "get_focuses_by_time",
            {"from_time": "2026-04-01T00:00:00Z", "to_time": "2026-04-30T23:59:59Z", "type": 1},
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"result": [{"id": "f1"}, {"id": "f2"}]})

    def test_focus_delete_command_passes_focus_id_and_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            ticktick_cli.save_config(
                path,
                ticktick_cli.Config(
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
            )

            stdout = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                mock.patch(
                    "cli.tool_commands.call_mcp_tool",
                    return_value={"structuredContent": {"id": "f1", "type": 0, "deleted": True}},
                ) as call_mcp_tool,
            ):
                result = ticktick_cli.main(
                    ["--config", str(path), "focus", "delete", "--focus-id", "f1", "--type", "0"]
                )

        self.assertEqual(result, 0)
        call_mcp_tool.assert_called_once_with(mock.ANY, "delete_focus", {"focus_id": "f1", "type": 0})
        self.assertEqual(json.loads(stdout.getvalue()), {"id": "f1", "type": 0, "deleted": True})

    def test_call_mcp_tool_initializes_then_calls_tool(self) -> None:
        requests: list[tuple[str, dict[str, str], dict[str, object]]] = []

        class FakeResponse:
            def __init__(self, payload: object, headers: dict[str, str] | None = None) -> None:
                self._body = b"" if payload is None else json.dumps(payload).encode("utf-8")
                self.headers = headers or {}

            def read(self) -> bytes:
                return self._body

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        responses = iter(
            [
                FakeResponse({"jsonrpc": "2.0", "id": "ticktick-cli-init", "result": {"protocolVersion": "2025-03-26"}}, {"Mcp-Session-Id": "session-1"}),
                FakeResponse(None, {}),
                FakeResponse({"jsonrpc": "2.0", "id": "ticktick-cli-get_user_preference", "result": {"structuredContent": {"time_zone": "Europe/Kiev"}}}, {}),
            ]
        )

        def fake_urlopen(request, timeout=0):
            requests.append(
                (
                    request.full_url,
                    dict(request.header_items()),
                    json.loads(request.data.decode("utf-8")),
                )
            )
            return next(responses)

        with mock.patch("cli.mcp.urllib.request.urlopen", side_effect=fake_urlopen):
            result = ticktick_cli.call_mcp_tool(
                ticktick_cli.Config(
                    mcp_url="https://mcp.ticktick.com/",
                    mcp_access_token="token",
                    mcp_token_expires_at=9999999999,
                ),
                "get_user_preference",
            )

        self.assertEqual(result, {"structuredContent": {"time_zone": "Europe/Kiev"}})
        self.assertEqual([payload["method"] for _, _, payload in requests], ["initialize", "notifications/initialized", "tools/call"])
        self.assertEqual(requests[0][0], "https://mcp.ticktick.com")
        self.assertEqual(requests[2][1]["Authorization"], "Bearer token")
        self.assertEqual(requests[2][1]["Mcp-session-id"], "session-1")
        self.assertEqual(requests[2][2]["params"], {"name": "get_user_preference", "arguments": {}})

    def test_parser_rejects_removed_flat_commands(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ticktick_cli.build_parser().parse_args(["tasks"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ticktick_cli.build_parser().parse_args(["projects"])


if __name__ == "__main__":
    unittest.main()

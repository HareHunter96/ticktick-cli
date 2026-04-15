"""Shared constants for the TickTick CLI."""


AUTHORIZE_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://api.ticktick.com/oauth/token"
REGISTER_URL = "https://api.ticktick.com/oauth/register"
MCP_URL = "https://mcp.ticktick.com/"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8080/"
DEFAULT_SCOPE = "tasks:read tasks:write"
DEFAULT_TIMEOUT = 30
CONFIG_ENV = "TICKTICK_CLI_CONFIG"
CLIENT_ID_ENV = "TICKTICK_CLIENT_ID"
CLIENT_SECRET_ENV = "TICKTICK_CLIENT_SECRET"
NAMESPACE_HELP = {
    "project": "Project commands",
    "task": "Task commands",
    "habit": "Habit commands",
    "focus": "Focus commands",
}
REPEATABLE_FLAG_OVERRIDES = {
    "task_ids": "task_id",
    "habit_ids": "habit_id",
}

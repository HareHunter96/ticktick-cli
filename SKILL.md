---
name: ticktick-cli
description: Install, authenticate, verify, and use the local TickTick CLI wrapper around TickTick MCP. Use when any agent should operate TickTick through the `ticktick` command instead of direct MCP calls, or when setting up this CLI globally for repeated agent workflows.
---

# TickTick CLI

This is a reusable agent workflow for the `ticktick-cli` repository. Use it when
the local `ticktick` command should be the interface to TickTick MCP. If your
agent runtime does not support installable skills, read this file directly and
follow the same steps.

## Safety

- Never print, inspect, paste, or commit TickTick tokens, client secrets, or the saved config file.
- The default config path is `~/.config/ticktick-cli/config.json`.
- Prefer command help and concise summaries over dumping full MCP payloads unless raw JSON is requested.

## Install

From the repository root, install for local development:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/ticktick --help
```

For repeated agent use, prefer a global command:

```sh
pipx install .
ticktick --help
```

If `pipx` is unavailable:

```sh
python3 -m pip install --user .
ticktick --help
```

If `ticktick` is still unavailable, use:

```sh
python3 ticktick_cli.py --help
```

## Authenticate

Run OAuth setup:

```sh
ticktick auth
```

Open the printed authorization URL, approve access, then paste the redirected URL
or raw OAuth code back into the CLI. A browser connection error on
`127.0.0.1:8080` after approval is expected; copy the URL from the address bar.

## Verify And Discover

Verify top-level commands:

```sh
ticktick --help
```

Use help-first discovery for command groups:

```sh
ticktick project --help
ticktick task --help
ticktick habit --help
ticktick focus --help
ticktick preference --help
```

After authentication, call the specific command shown by help for the user's task.

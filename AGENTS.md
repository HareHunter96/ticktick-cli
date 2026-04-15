# Agent Guide

This repository contains a small dependency-free CLI wrapper around TickTick MCP.
The local `ticktick` command exposes TickTick MCP tools through shell-friendly
commands after OAuth authentication.

## Setup

Install the CLI from the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/ticktick --help
```

Prefer making `ticktick` available globally when the task requires repeated use:

```sh
pipx install .
```

If `pipx` is unavailable, use a Python user install:

```sh
python3 -m pip install --user .
```

Verify the command:

```sh
ticktick --help
```

Fallback when the global command is unavailable:

```sh
python3 ticktick_cli.py --help
```

## Authentication

Authenticate before calling MCP-backed commands:

```sh
ticktick auth
```

The command prints an authorization URL and asks for the redirected URL or raw
OAuth code after browser approval.

Never print, inspect, paste, or commit saved credentials or tokens. The default
config path is:

```text
~/.config/ticktick-cli/config.json
```

## Agent Skill

This repository also includes a reusable agent skill at [`./SKILL.md`](./SKILL.md).
If your agent runtime supports skills, install or load it. Otherwise, read it as a
compact workflow for installing, authenticating, verifying, and operating this
TickTick CLI.

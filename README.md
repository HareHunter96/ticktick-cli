# TickTick CLI

Small dependency-free CLI wrapper around TickTick MCP.

The project exposes TickTick MCP tools through a local `ticktick` command, so agents
and shell workflows can authenticate once and call MCP-backed commands from the CLI.

## Install

From the project folder:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/ticktick --help
```

You can also run the CLI directly:

```sh
python3 ticktick_cli.py --help
```

## Global Command

Recommended with `pipx`:

```sh
pipx install .
ticktick --help
```

Alternative user install:

```sh
python3 -m pip install --user .
ticktick --help
```

If `ticktick` is not found after `--user` install, make sure Python's user scripts
directory is on your `PATH`.

## CLI Help

```sh
ticktick --help
```

Top-level commands:

```text
auth
preference
project
task
habit
focus
```

Command groups expose their own help:

```sh
ticktick project --help
ticktick task --help
ticktick habit --help
ticktick focus --help
```

## Verify

Run the unit test suite:

```sh
python3 -m unittest discover -s tests -v
```

Before publishing or relying on a global install, verify the wheel in a clean
environment:

```sh
python3 -m pip wheel . --no-deps -w /tmp/ticktick-cli-wheel-check
python3 -m venv /tmp/ticktick-cli-install-check
/tmp/ticktick-cli-install-check/bin/pip install /tmp/ticktick-cli-wheel-check/ticktick_cli-0.1.0-py3-none-any.whl
/tmp/ticktick-cli-install-check/bin/ticktick --help
```

## Authentication

`ticktick auth` uses the TickTick MCP OAuth flow.

```sh
ticktick auth
```

The command prints an authorization URL, asks you to approve access in the browser,
then waits for the redirected URL or raw OAuth `code`.

By default the CLI registers an MCP OAuth client automatically. Optional manual
credentials can be provided with:

```text
--client-id
--client-secret
```

Useful auth flags:

```text
--redirect-uri
--url
--resource
--public-client
--show-secret-input
```

Default redirect URI:

```text
http://127.0.0.1:8080/
```

The browser may show a connection error after approval because nothing is listening
on `127.0.0.1:8080`. That is expected. Copy the full browser URL and paste it back
into the CLI.

## Config

Credentials and tokens are stored at:

```text
~/.config/ticktick-cli/config.json
```

Override the config path with:

```sh
TICKTICK_CLI_CONFIG=/path/to/config.json ticktick auth
```

The config file contains secrets. Do not commit it.

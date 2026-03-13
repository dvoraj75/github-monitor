# `daemon.py` -- API reference

Module: `forgewatch.daemon`

The main orchestrator that wires together all components: configuration
loading, GitHub API polling, state management, desktop notifications, D-Bus
service registration, and Unix signal handling.

## `Daemon`

The central class that manages the daemon lifecycle.

### Constructor

```python
Daemon(config: Config, config_path: Path | None = None)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `config` | `Config` | (required) | Validated configuration (from `load_config()`) |
| `config_path` | `Path \| None` | `None` | Original config file path (used on SIGHUP reload to re-read the same file) |

Creates the following internal components:

| Attribute | Type | Description |
|---|---|---|
| `config` | `Config` | Current configuration (reassigned on SIGHUP reload) |
| `config_path` | `Path \| None` | Config file path passed at construction (used by `_reload_config()`) |
| `store` | `PRStore` | In-memory state store for tracked PRs |
| `client` | `GitHubClient` | Async GitHub API client (initialized with `base_url` and `max_retries` from config) |
| `bus` | `MessageBus \| None` | D-Bus connection (set during `start()` if D-Bus is enabled) |
| `interface` | `ForgewatchInterface \| None` | D-Bus interface (set during `start()` if D-Bus is enabled) |

### `async start() -> None`

Initialise all components and enter the poll loop. This method blocks until
a shutdown signal is received. The startup sequence is:

1. Start the GitHub client (creates an `aiohttp` session)
2. Set up the D-Bus service (if `config.dbus_enabled` is `True`)
3. Register Unix signal handlers (`SIGTERM`, `SIGINT`, `SIGHUP`)
4. Enter the poll loop

If `config.dbus_enabled` is `False`, the D-Bus setup is skipped entirely and
the daemon runs without a D-Bus interface. This is useful for headless setups,
containers, or SSH sessions where D-Bus is unavailable.

### `async stop() -> None`

Clean shutdown: close the HTTP session and disconnect from D-Bus. Should
always be called after `start()` returns -- typically in a `try/finally` block.

### `async _poll_loop() -> None`

Main polling loop. Repeatedly calls `_poll_once()` and then waits for the
configured `poll_interval` seconds before polling again.

Uses `asyncio.wait()` with two event tasks -- a shutdown event and a reload
event -- so that both SIGTERM/SIGINT (shutdown) and SIGHUP (config reload) can
wake the loop immediately rather than blocking up to `poll_interval` seconds.
On shutdown the loop exits; on reload it re-polls immediately with the new
configuration.

### `async _poll_once() -> None`

Single poll cycle:

1. `client.fetch_all()` -- fetch all review-requested and assigned PRs
2. `store.update(prs)` -- compute the diff against previous state
3. If there are new PRs **and** notifications are enabled **and** (this is not
   the first poll **or** `notify_on_first_poll` is `True`):
   `notify_new_prs(diff.new_prs, threshold=..., urgency=...)`
4. If the diff has any changes and D-Bus is connected:
   emit `interface.PullRequestsChanged()`

**Notification control:**

- `config.notifications_enabled` -- master toggle; if `False`, no desktop
  notifications are sent regardless of other settings
- `config.notify_on_first_poll` -- if `True`, the first poll cycle can send
  notifications (default: `False` to avoid a flood on startup)
- `config.notification_threshold` -- passed to `notify_new_prs()` as the
  `threshold` parameter (individual vs. summary notification cutoff)
- `config.notification_urgency` -- passed to `notify_new_prs()` as the
  `urgency` parameter
- `config.notifications.grouping` -- passed to `notify_new_prs()` as the
  `grouping` parameter (`"flat"` or `"repo"`)
- `config.notifications.repos` -- passed to `notify_new_prs()` as the
  `repo_overrides` parameter (`None` if the dict is empty)

**First-poll notification suppression:** On the very first poll cycle, all PRs
appear as "new" because the store starts empty. By default
(`notify_on_first_poll=False`), desktop notifications are suppressed for the
first cycle. The D-Bus signal is still emitted so that external tools can
populate their state.

**Error handling:** All exceptions during a poll cycle are caught and logged.
The daemon continues running and retries on the next cycle.

### `_handle_shutdown() -> None`

Synchronous handler for `SIGTERM` and `SIGINT`. Sets `_running = False` and
signals the shutdown event to wake the poll loop immediately.

### `_handle_reload() -> None`

Synchronous handler for `SIGHUP`. Schedules an async config reload task on
the running event loop (signal handlers cannot be async). On successful reload,
the reload event is set, waking the poll loop for an immediate re-poll with the
new configuration.

### `async _reload_config() -> None`

Reload the configuration file and recreate the HTTP session:

1. Call `load_config(self.config_path)` -- uses the original `-c` path if one
   was provided at startup, otherwise falls back to default path resolution
2. Apply the new log level immediately via
   `logging.getLogger().setLevel(config.log_level)`
3. Close the current aiohttp session
4. Call `client.update_config()` with the new token, username, repos, base URL,
   and max retries
5. Start a fresh aiohttp session (picks up new token/headers)

If any step fails, the error is logged and the daemon continues with its
previous configuration.

## Data flow

```
Timer fires
    │
    ▼
Daemon._poll_once()
    │
    ├── client.fetch_all()      ──► GitHub Search API
    │
    ├── store.update(prs)       ──► StateDiff
    │
    ├── if new PRs AND notifications_enabled AND (not first_poll OR notify_on_first_poll):
    │   └── notify_new_prs(threshold=..., urgency=..., grouping=..., repo_overrides=...)  ──► notify-send
    │
    └── if any changes AND dbus connected:
        └── interface.PullRequestsChanged()  ──► D-Bus signal
```

## Signal handling

| Signal | Handler | Behaviour |
|---|---|---|
| `SIGTERM` | `_handle_shutdown()` | Graceful shutdown -- exits poll loop immediately |
| `SIGINT` | `_handle_shutdown()` | Same as SIGTERM (Ctrl+C in terminal) |
| `SIGHUP` | `_handle_reload()` | Reload config from disk (respects `-c` path), apply log level, recreate HTTP session, wake poll loop for immediate re-poll |

## Usage example

```python
import asyncio
from pathlib import Path
from forgewatch.config import load_config
from forgewatch.daemon import Daemon

config_path = Path("/path/to/config.toml")
config = load_config(config_path)
daemon = Daemon(config, config_path)

async def run():
    try:
        await daemon.start()
    finally:
        await daemon.stop()

asyncio.run(run())
```

This is essentially what `__main__.py` does, with the addition of argument
parsing and logging setup.

## CLI entry point (`__main__.py`)

The `main()` function in `__main__.py` is the single entry point for all
`forgewatch` invocations.  A unified argument parser exposes both daemon
flags (`-c`, `-v`) and management subcommands (`setup`, `service`, `uninstall`,
`completions`) so that `forgewatch --help` shows everything:

```
usage: forgewatch [-h] [-c CONFIG] [-v] {setup,service,uninstall,completions} ...

ForgeWatch — GitHub PR Monitor

positional arguments:
  {setup,service,uninstall,completions}
    setup               Initial setup wizard
    service             Manage systemd services
    uninstall           Remove services and optionally config
    completions         Generate shell completions

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to config.toml
  -v, --verbose         Enable debug logging

Run without a command to start the daemon.
```

The parser is built by `build_full_parser()`, which calls
`cli.add_subcommands()` to register the management subcommands.  After
parsing, `main()` checks `args.command`:

- **Not `None`** — dispatches to `cli.dispatch(args)` (management CLI).
- **`None`** — runs the daemon via `_run_daemon(args)`.

### Management subcommands

```bash
forgewatch setup                # interactive setup wizard
forgewatch setup --config-only  # only create config.toml
forgewatch setup --service-only # only install + start systemd services
forgewatch service <action>     # start | stop | restart | status | install | enable | disable
forgewatch uninstall            # remove services, optionally remove config
forgewatch completions <shell>  # generate shell completions (bash, zsh, tcsh)
```

See [cli module docs](cli.md) for the full API reference.

### Daemon mode

| Flag | Description |
|---|---|
| `-c`, `--config` | Path to a TOML config file (overrides default path resolution) |
| `-v`, `--verbose` | Set log level to DEBUG (overrides `config.log_level`) |

Basic logging (INFO level, or DEBUG with `-v`) is initialised **before** config
loading so that any `ConfigError` is properly formatted rather than producing a
raw traceback. If the config file is missing, the error message suggests
running `forgewatch setup`; if the config is invalid, it suggests checking the
config file. In both cases the daemon exits cleanly with code 1.

After a successful config load, the log level is reconfigured to the value
from `config.log_level` (or DEBUG if `-v` was passed).

The entry point is registered in `pyproject.toml` as `forgewatch`, so
after installation it can be invoked directly:

```bash
forgewatch                          # run with defaults
forgewatch -v                       # debug logging
forgewatch -c /path/to/config.toml  # custom config
```

## Design notes

- The poll loop uses `asyncio.wait()` with two event tasks (shutdown and
  reload) rather than `asyncio.sleep()`. This makes both shutdown and config
  reload immediate -- the shutdown event is set by the SIGTERM/SIGINT handler,
  and the reload event is set after a successful SIGHUP config reload, either
  of which wakes the wait without blocking for the remaining poll interval
- First-poll notification suppression prevents a burst of notifications when
  the daemon starts with many existing review requests. The D-Bus signal still
  fires so panel plugins can populate their state. This can be overridden via
  `notify_on_first_poll = true` in the config
- SIGHUP config reload closes and restarts the HTTP session to ensure a new
  token (if changed) is picked up in the session headers. On success, the
  reload event wakes the poll loop so the new settings (including
  `poll_interval`) take effect immediately with a fresh poll cycle. The reload
  is scheduled as a task because signal handlers cannot be async
- Config reload uses `self.config_path` (set at construction time) to ensure
  the same file is re-read on reload, even when the daemon was started with
  `-c /custom/path`
- The log level is applied immediately on reload, allowing runtime log level
  changes without restarting the daemon
- D-Bus setup is conditional on `config.dbus_enabled`, allowing the daemon to
  run in environments where D-Bus is unavailable
- The `_reload_config()` task stores a reference via `add_done_callback()` to
  prevent garbage collection before completion (ruff RUF006)
- All poll cycle errors are caught and logged -- the daemon never crashes from
  a transient GitHub API failure

# AGENTS.md — AI Coding Agent Guide

This file describes how AI coding agents should work with the `github-monitor` codebase.

## Project Overview

**github-monitor** is a Python 3.13+ async daemon that monitors GitHub pull requests assigned to (or requesting review from) a specific user. It exposes live state over D-Bus and sends desktop notifications via `notify-send` when new PRs arrive. An optional system tray indicator (separate process) connects to the daemon over D-Bus to display a live PR count and a clickable popup window.

Key traits:
- Pure async (`asyncio`) -- no threads, no blocking I/O in the main loop
- Frozen dataclasses for data models
- `aiohttp` for HTTP, `dbus-next` for D-Bus, `notify-send` (libnotify) for desktop notifications
- Single-user daemon designed to run as a systemd user service
- Optional GTK3/AppIndicator3 system tray indicator with `gbulb` event loop integration

## Architecture

```
__main__.py          CLI entry point -- dispatches to CLI subcommands or daemon
    |
    +---> cli/               Management subcommands (setup, service, uninstall)
    |       __init__.py      Argparse parser + run_cli() dispatch
    |       setup.py         Interactive setup wizard (config + systemd)
    |       service.py       Systemd service management (start/stop/status/...)
    |       uninstall.py     Uninstall flow (stop services, remove files)
    |       _output.py       Coloured terminal output helpers
    |       _prompts.py      Interactive prompt helpers (ask_string, ask_yes_no, ...)
    |       _checks.py       System dependency checks (notify-send, D-Bus, GTK, systemctl)
    |       _systemd.py      Systemd operations (install/remove units, start/stop/reload)
    |       systemd/         Bundled .service files (accessed via importlib.resources)
    |
    v
daemon.py            Orchestrator -- wires poller, store, D-Bus, notifier
    |                Handles SIGTERM/SIGINT (shutdown), SIGHUP (config reload)
    |                Poll loop: fetch -> diff -> notify -> D-Bus signal
    |
    +---> poller.py          GitHub API client (aiohttp) + PullRequest dataclass
    +---> store.py           In-memory PR state + diff computation (StateDiff)
    +---> notifier.py        Desktop notifications via notify-send subprocess
    +---> dbus_service.py    D-Bus session bus interface (org.github_monitor.Daemon)
    +---> config.py          TOML config loading/validation
    +---> url_opener.py      Shared URL opener (XDG portal + xdg-open fallback)

indicator/               Separate process -- system tray icon + popup window
    __main__.py          Entry point -- dependency checks, gbulb install, launch
    app.py               Orchestrator -- wires D-Bus client, tray, popup window
    +---> client.py      D-Bus client -- connects to daemon, subscribes to signals
    +---> tray.py        AppIndicator3 tray icon with PR count label
    +---> window.py      GTK3 popup window with scrollable PR list
    +---> models.py      PRInfo + DaemonStatus frozen dataclasses
    +---> _tray_state.py     Pure state logic (icon selection, label formatting, tooltip text)
    +---> _window_helpers.py Pure helpers (relative time, sorting, markup escaping)
```

### Module Responsibilities

| Module | Role |
|---|---|
| `__main__.py` | CLI entry point. Builds a unified argparse parser with daemon flags (`-c`, `-v`) and management subcommands (`setup`, `service`, `uninstall`). When `args.command` is set, dispatches to `cli.dispatch()`. Otherwise starts the daemon. |
| `cli/__init__.py` | Registers subcommands via `add_subcommands()`, dispatches via `dispatch()`. Also provides `build_parser()` and `run_cli()` for standalone/test use. |
| `cli/setup.py` | Interactive setup wizard. Config file creation (token, username, poll interval, repos), systemd service installation, and enable+start. Supports `--config-only` and `--service-only` flags. |
| `cli/service.py` | Thin CLI layer over `_systemd.py`. Actions: `install`, `start`, `stop`, `restart`, `status`, `enable`, `disable`. Manages both daemon and indicator services. |
| `cli/uninstall.py` | Uninstall flow. Stops and disables services, removes systemd unit files and legacy autostart entry, optionally removes config directory. |
| `cli/_output.py` | Coloured terminal output helpers (`info`, `ok`, `warn`, `err`, `step`). Colour suppressed when stdout is not a TTY. |
| `cli/_prompts.py` | Interactive prompt helpers (`ask_string`, `ask_yes_no`, `ask_int`, `ask_list`). Input validation with retry loops. |
| `cli/_checks.py` | System dependency checks (`check_notify_send`, `check_dbus_session`, `check_gtk_indicator`, `check_systemctl`). |
| `cli/_systemd.py` | All systemd interactions: install/remove service files, daemon-reload, start/stop/restart/enable/disable, status queries, legacy autostart cleanup. |
| `config.py` | Loads `config.toml`, validates fields, supports env var overrides (`GITHUB_TOKEN`). |
| `daemon.py` | Main `Daemon` class. Lifecycle: `start()` -> poll loop -> `stop()`. Signal handlers for graceful shutdown and config reload. |
| `poller.py` | `PullRequest` frozen dataclass (core data model) + `GitHubClient` async HTTP client. Uses GitHub Search Issues API with pagination, rate limiting, exponential backoff retries. |
| `store.py` | `PRStore` -- in-memory dict keyed by URL. Computes `StateDiff` (new/closed/updated PRs) on each update. |
| `notifier.py` | Sends desktop notifications. 1-3 PRs get individual notifications; >3 get a single summary. Downloads PR author avatars for notification icons. Supports clickable notifications that open the PR in a browser. |
| `dbus_service.py` | Exports `org.github_monitor.Daemon` on the session bus. Methods: `GetPullRequests()`, `GetStatus()`, `Refresh()`. Signal: `PullRequestsChanged`. |
| `url_opener.py` | Shared async URL opener used by both the notifier and indicator. Tries XDG Desktop Portal (D-Bus) first, falls back to `xdg-open`. |
| `indicator/__main__.py` | Indicator entry point. Checks for GTK3/AppIndicator3/gbulb dependencies, installs gbulb event loop, launches `IndicatorApp`. |
| `indicator/app.py` | `IndicatorApp` orchestrator. Wires D-Bus client, tray icon, and popup window. Bridges sync GTK callbacks and async D-Bus calls. |
| `indicator/client.py` | `DaemonClient` -- async D-Bus client that connects to the daemon, subscribes to `PullRequestsChanged`, auto-reconnects on disconnect. |
| `indicator/tray.py` | `TrayIcon` -- AppIndicator3 system tray icon with PR count label, colour-coded icons, and a GTK menu (Show/Hide PRs, Refresh, Quit). |
| `indicator/window.py` | `PRWindow` -- GTK3 popup window with header, scrollable PR list (clickable rows), and status footer. |
| `indicator/models.py` | `PRInfo` and `DaemonStatus` frozen dataclasses for data received from the daemon over D-Bus. |
| `indicator/_tray_state.py` | Pure functions for icon name selection, label formatting, and tooltip text. No GTK imports -- testable without system packages. |
| `indicator/_window_helpers.py` | Pure functions for relative time formatting, PR sorting, status text, and Pango markup escaping. No GTK imports. |

## Tech Stack

- **Runtime**: Python 3.13+
- **Package manager**: [uv](https://docs.astral.sh/uv/)
- **Async HTTP**: `aiohttp` (for GitHub API calls and avatar downloads)
- **D-Bus**: `dbus-next` (async D-Bus client/server)
- **Desktop notifications**: `notify-send` (from `libnotify-bin`)
- **System tray indicator** (optional): GTK3 + AppIndicator3 (system packages) + `gbulb` (GLib/asyncio event loop integration)
- **Build backend**: `hatchling`
- **CI**: GitHub Actions — two parallel jobs on push/PR to `main`/`develop`: lint & type check (ruff, mypy, ShellCheck, lockfile verification) and test & audit (pytest, pip-audit)
- **Pre-commit hooks**: ruff + mypy via `pre-commit`

## Build & Run

```bash
# Install dependencies
uv sync

# Run the daemon (development)
uv run github-monitor -c config.toml
uv run github-monitor -c config.toml -v   # debug logging

# Run as module
uv run python -m github_monitor -c config.toml

# CLI management commands
uv run github-monitor setup                     # full setup wizard
uv run github-monitor setup --config-only       # only create config.toml
uv run github-monitor setup --service-only      # only install + start systemd services
uv run github-monitor service status             # show service status
uv run github-monitor service start              # start services
uv run github-monitor service stop               # stop services
uv run github-monitor service restart            # restart services
uv run github-monitor service install            # install systemd unit files
uv run github-monitor service enable             # enable autostart
uv run github-monitor service disable            # disable autostart
uv run github-monitor uninstall                  # remove services + optionally config

# Install as systemd user service
systemctl --user enable --now github-monitor
```

## Testing

```bash
# Run all tests (parallel, with coverage)
uv run pytest

# Run a specific test file
uv run pytest tests/test_notifier.py

# Run a specific test class or method
uv run pytest tests/test_notifier.py::TestNotifyNewPrsIndividual::test_single_pr_notification

# Run with verbose output
uv run pytest -v
```

Test configuration (in `pyproject.toml`):
- `asyncio_mode = "auto"` — async test functions are detected automatically
- `addopts = "-ra -v --cov=github_monitor --cov-report=term -n auto"` — parallel execution via `pytest-xdist`, coverage via `pytest-cov`
- Mock HTTP with `aioresponses`
- Mock subprocesses and D-Bus with `unittest.mock`

### Test Patterns

- Each test file has a `_make_pr()` helper that builds `PullRequest` instances with sensible defaults
- `aioresponses` is used to mock GitHub API responses in `test_poller.py`
- `asyncio.create_subprocess_exec` is patched in `test_notifier.py` to mock `notify-send`
- D-Bus methods are accessed via `_unwrap_method()` / `_unwrap_signal()` helpers in `test_dbus_service.py` (because `dbus-next` decorators wrap methods)

## Linting & Type Checking

```bash
# Lint (ruff — all rules enabled with specific ignores)
uv run ruff check .
uv run ruff check --fix .    # auto-fix

# Format (ruff — black-compatible)
uv run ruff format .

# Type check (mypy — strict mode)
uv run mypy github_monitor
```

### Ruff Configuration

- `target-version = "py313"`
- `line-length = 120`
- `select = ["ALL"]` with ignores: `D` (docstrings), `ANN` (annotations — mypy handles this), `COM812`, `ISC001`
- Test files additionally ignore: `S101`, `S105`, `S106`, `PLR2004`, `SLF001`, `INP001`, `ARG001`

### Mypy Configuration

- `python_version = "3.13"`
- `strict = true`
- `warn_return_any = true`

## Coding Conventions

1. **Imports**: Use `from __future__ import annotations` in every file. Use `TYPE_CHECKING` guard for import-only-at-type-check-time types.
2. **Data models**: Frozen dataclasses (`@dataclass(frozen=True)`).
3. **Async**: All I/O is async. Use `asyncio.create_subprocess_exec` for subprocesses, `aiohttp.ClientSession` for HTTP.
4. **Error handling**: Catch and log exceptions in the poll loop — never let a single cycle crash the daemon. Use specific exception types (e.g., `AuthError`, `ConfigError`).
5. **Naming**: Module-level private constants use `_UPPER_SNAKE`. Private methods use `_lower_snake`. D-Bus methods use `PascalCase` (D-Bus convention).
6. **Logging**: Use `logging.getLogger(__name__)` per module. Debug for routine info, warning for recoverable issues, error/exception for failures.
7. **Type hints**: Full type hints everywhere. Use `str | None` union syntax (not `Optional`). Use `list[X]` (not `List[X]`).

## Key Files Quick Reference

| File | What to Know |
|---|---|
| `config.toml` | **NEVER commit this file** -- contains a real GitHub token. Use `config.example.toml` as reference. |
| `config.example.toml` | Template config with placeholder values. Safe to commit. |
| `pyproject.toml` | Build config, dependencies, tool settings (ruff, mypy, pytest). |
| `systemd/github-monitor.service` | Systemd user unit file for the daemon. |
| `systemd/github-monitor-indicator.service` | Systemd user unit file for the indicator. Depends on the daemon service. |
| `github_monitor/indicator/` | System tray indicator package. Separate process, connects to daemon over D-Bus. Requires GTK3/AppIndicator3/gbulb. |
| `github_monitor/cli/` | CLI management subcommands package. Setup wizard, service management, uninstall. Stdlib only (no extra deps). |
| `github_monitor/cli/systemd/` | Bundled `.service` files accessed via `importlib.resources`. |
| `github_monitor/url_opener.py` | Shared URL opener (XDG portal + xdg-open fallback). Used by both notifier and indicator. |
| `install.sh` | **DEPRECATED.** Automated installer -- use `github-monitor setup` instead. |
| `update.sh` | **DEPRECATED.** Update script -- use `pip install --upgrade github-monitor` instead. |
| `uninstall.sh` | **DEPRECATED.** Uninstall script -- use `github-monitor uninstall` instead. |
| `docs/` | Architecture, configuration, development, and module documentation. |

## Common Modification Patterns

### Adding a field to PullRequest

1. Add the field to the `PullRequest` dataclass in `poller.py`
2. Update `_parse_pr()` in `poller.py` to extract it from the GitHub API response
3. Update `_serialize_pr()` in `dbus_service.py` to include it in JSON output
4. Update `_make_pr()` helpers in **all** test files (`test_notifier.py`, `test_poller.py`, `test_daemon.py`, `test_dbus_service.py`, `test_store.py`)
5. Update any direct `PullRequest()` constructor calls in tests

### Adding a new notification feature

1. Modify `notifier.py` — update `_send_notification()` or `notify_new_prs()`
2. Update tests in `test_notifier.py`
3. If it affects the poll cycle, check `daemon.py` integration

### Adding a D-Bus method

1. Add the method to `GithubMonitorInterface` in `dbus_service.py` with `@method()` decorator
2. Use D-Bus type signature strings in the return annotation (e.g., `-> "s"`)
3. Add tests using the `_unwrap_method()` helper pattern in `test_dbus_service.py`

### Modifying configuration

1. Add the field to the `Config` dataclass in `config.py`
2. Add validation in `_validate()`
3. Update `config.example.toml`
4. Update tests in `test_config.py`

### Adding/modifying the indicator

The indicator is a separate process (`github_monitor.indicator`) with its own
entry point, D-Bus client, and GTK widgets. Key patterns:

1. **Pure logic** is in `_tray_state.py` and `_window_helpers.py` -- these have
   zero GTK imports and are fully unit-testable without system packages.
2. **GTK widgets** are in `tray.py` and `window.py` -- test via mocking `gi.repository`.
3. **D-Bus client** is in `client.py` -- test by mocking `dbus_next.aio.message_bus.MessageBus`.
4. **Orchestrator** is in `app.py` -- test by injecting mock client/tray/window.
5. **Models** (`PRInfo`, `DaemonStatus`) are in `models.py` -- separate from
   the daemon's `PullRequest` dataclass because the indicator should not import
   daemon internals.

When modifying the D-Bus wire format (e.g. adding a field to `_serialize_pr()`
in `dbus_service.py`), also update:
- `client.py` `_parse_pr()` to handle the new field
- `models.py` `PRInfo` dataclass to include the new field

### Adding/modifying CLI subcommands

The CLI package (`github_monitor.cli`) uses stdlib only (no extra deps). Key patterns:

1. **Shared helpers** are in `_output.py`, `_prompts.py`, `_checks.py`, and
   `_systemd.py`. These are pure-Python modules with no async code.
2. **Subcommand handlers** are in `setup.py`, `service.py`, and `uninstall.py`.
   Each exports a single `run_*()` entry point.
3. **Parser and dispatch** are in `__init__.py` (`add_subcommands()` + `dispatch()`).
   `build_parser()` and `run_cli()` are also provided for standalone/test use.
   Subcommand modules are imported lazily inside `dispatch()` to avoid loading
   unused code.
4. **Unified parser** in `__main__.py` builds a single argparse parser with both
   daemon flags (`-c`, `-v`) and management subcommands. When `args.command` is
   not `None`, it dispatches to `cli.dispatch(args)`.
5. **Bundled service files** live in `cli/systemd/` and are read via
   `importlib.resources.files("github_monitor.cli.systemd")`.

When adding a new CLI subcommand:
1. Create `cli/<command>.py` with a `run_<command>()` entry point
2. Add the subparser in `add_subcommands()` in `cli/__init__.py`
3. Add the dispatch case in `dispatch()` in `cli/__init__.py`
4. Add tests in `tests/test_cli_<command>.py`

## Security Notes

- `config.toml` contains a real GitHub personal access token — it is listed in `.gitignore` and must never be committed
- The token can alternatively be provided via `GITHUB_TOKEN` environment variable
- The systemd service file uses `ProtectSystem=strict` and `ProtectHome=read-only` for security hardening

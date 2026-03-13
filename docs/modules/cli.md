# `cli/` -- API reference

Package: `forgewatch.cli`

CLI management subcommands for installing and managing ForgeWatch as a
systemd user service. Most subcommands use **stdlib only**; the `completions`
subcommand uses `shtab` for shell-completion generation.

## Command overview

```
forgewatch setup [--config-only | --service-only]
forgewatch service {install,start,stop,restart,status,enable,disable}
forgewatch uninstall
forgewatch completions {bash,zsh,tcsh}
```

When the first argument to `forgewatch` is a known subcommand (`setup`,
`service`, `uninstall`, `completions`), the unified parser in `__main__.py`
dispatches to `cli.dispatch()`. Otherwise, the daemon starts as usual for
full backward compatibility. Running `forgewatch --help` shows both daemon
flags and management subcommands.

## Module structure

```
cli/
├── __init__.py      # build_parser() + run_cli() -- subcommand argument parser
├── setup.py         # "setup" command implementation
├── service.py       # "service" command implementation
├── uninstall.py     # "uninstall" command implementation
├── _output.py       # Coloured terminal output helpers
├── _prompts.py      # Interactive prompt helpers
├── _checks.py       # System dependency checks
├── _systemd.py      # Systemd operations (copy units, start/stop/reload)
└── systemd/         # Bundled .service files (accessed via importlib.resources)
    ├── forgewatch.service
    └── forgewatch-indicator.service
```

---

## `cli/__init__.py` -- Parser and dispatch

### `add_subcommands(subparsers) -> None`

Add CLI management subcommands to an existing subparsers group. This is called
by `__main__.build_full_parser()` to register subcommands on the unified parser.

| Parameter | Type | Description |
|---|---|---|
| `subparsers` | `argparse._SubParsersAction` | A subparsers action (from `parser.add_subparsers()`) |

### `dispatch(args: argparse.Namespace) -> None`

Dispatch to the appropriate CLI subcommand handler given a pre-parsed namespace.
Called by `__main__.main()` when `args.command` is not `None`.

| Parameter | Type | Description |
|---|---|---|
| `args` | `argparse.Namespace` | Pre-parsed arguments with a `command` attribute |

Dispatch targets (lazy-imported inside the function body):

| Command | Handler |
|---|---|
| `setup` | `setup.run_setup(config_only=..., service_only=...)` |
| `service` | `service.run_service(action=...)` |
| `uninstall` | `uninstall.run_uninstall()` |
| `completions` | `shtab.complete(parser, args.shell)` (inline, uses `build_full_parser()`) |

### `build_parser() -> argparse.ArgumentParser`

Build a standalone argparse parser for CLI management subcommands. Uses
`add_subcommands()` internally. This parser does **not** include daemon flags
(`-c`, `-v`) -- those live on the unified parser in `__main__.py`.

Returns an `ArgumentParser` with four subcommands:

| Subcommand | Arguments | Description |
|---|---|---|
| `setup` | `--config-only`, `--service-only` (mutually exclusive) | Interactive setup wizard |
| `service` | `action` (positional, choices: `install`, `start`, `stop`, `restart`, `status`, `enable`, `disable`) | Manage systemd services |
| `uninstall` | *(none)* | Remove services and optionally config |
| `completions` | `shell` (positional, choices: `bash`, `zsh`, `tcsh`) | Generate shell completions |

### `run_cli(argv: list[str] | None = None) -> None`

Parse arguments and dispatch to the appropriate subcommand handler. Convenience
wrapper around `build_parser()` + `dispatch()`, used by tests.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `argv` | `list[str] \| None` | `None` | Command-line arguments to parse. Defaults to `sys.argv[1:]`. |

When `command` is `None` (no subcommand given), prints help and exits with code 1.

---

## `cli/setup.py` -- Setup command

Module: `forgewatch.cli.setup`

Interactive setup wizard that replaces the functionality of the deprecated
`install.sh` script.

### `run_setup(*, config_only: bool = False, service_only: bool = False) -> None`

Entry point for the `forgewatch setup` command.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `config_only` | `bool` | `False` | Only create the config file, skip service steps |
| `service_only` | `bool` | `False` | Only install and start services, skip config wizard |

**Full setup flow (no flags):**

| Step | Description |
|---|---|
| 1 | **Dependency checks** -- `check_notify_send()`, `check_dbus_session()`, `check_gtk_indicator()`, `check_systemctl()` |
| 2 | **Config wizard** -- prompts for token, username, poll interval, repos; writes `config.toml` with `chmod 600` |
| 3 | **Install systemd services** -- `install_service_files(include_indicator=has_gtk)` |
| 4 | **Enable and start services** -- enables + starts daemon (and indicator if GTK available) |
| 5 | **Summary** -- prints config path and useful commands |

With `--config-only`: steps 3-4 are skipped, systemctl is not checked.
With `--service-only`: step 2 (config wizard) is skipped.

### Internal helpers

#### `_format_repos_toml(repos: list[str]) -> str`

Format a list of repo strings as a TOML inline array literal.

```python
_format_repos_toml([])                    # '[]'
_format_repos_toml(["owner/repo"])        # '["owner/repo"]'
_format_repos_toml(["a/b", "c/d"])        # '["a/b", "c/d"]'
```

#### `_write_config(token: str, username: str, poll_interval: int, repos: list[str]) -> None`

Write the config file to `CONFIG_PATH` (`~/.config/forgewatch/config.toml`)
using `_CONFIG_TEMPLATE`. Creates the config directory if needed. Sets file
permissions to `0o600` (owner read/write only).

#### `_config_wizard() -> None`

Run the interactive config wizard. If a config file already exists, prompts
the user to confirm overwrite (default: no). Prompts for:

| Field | Prompt function | Validation |
|---|---|---|
| `github_token` | `ask_string(..., required=True)` | Non-empty |
| `github_username` | `ask_string(..., required=True)` | Non-empty |
| `poll_interval` | `ask_int(..., default=300, minimum=30)` | Integer >= 30 |
| `repos` | `ask_list(...)` | Comma-separated, empty = all repos |

#### `_start_or_restart(service: str) -> None`

Start a service, or restart it if already active. Used during setup to handle
both fresh installs and re-runs.

#### `_install_and_start_services(*, has_gtk: bool, step_install: int, step_start: int, total: int) -> None`

Install, enable, and start systemd services. If `has_gtk` is `True`, the
indicator service is also installed, enabled, and started.

#### `_print_summary(*, has_gtk: bool, has_systemctl: bool) -> None`

Print the final summary with config file path and useful `systemctl` /
`journalctl` commands.

---

## `cli/service.py` -- Service management command

Module: `forgewatch.cli.service`

Thin CLI layer over `_systemd.py` for managing the daemon and indicator
systemd services. Replaces the manual `systemctl` commands users had to
type directly.

### `run_service(action: str) -> None`

Execute a service management action.

| Parameter | Type | Description |
|---|---|---|
| `action` | `str` | One of: `install`, `start`, `stop`, `restart`, `status`, `enable`, `disable` |

Checks for `systemctl` availability first and exits with code 1 if not found.
Dispatches to the appropriate action handler via the `_ACTIONS` dictionary.

### Actions

| Action | Handler | Behaviour |
|---|---|---|
| `install` | `_action_install()` | Check for GTK, install service files (daemon + indicator if GTK available) |
| `start` | `_action_start()` | Start daemon. If indicator service file is installed, start indicator too. |
| `stop` | `_action_stop()` | Stop indicator (if active) first, then stop daemon. |
| `restart` | `_action_restart()` | Restart daemon. If indicator is active, restart indicator too. |
| `status` | `_action_status()` | Print `systemctl status` for daemon. If indicator service file is installed, also print indicator status. |
| `enable` | `_action_enable()` | Enable daemon for autostart. If indicator service file is installed, enable indicator too. |
| `disable` | `_action_disable()` | Disable indicator (if installed) first, then disable daemon. |

### Internal helpers

#### `_require_systemctl() -> bool`

Check that `systemctl` is available on PATH. Prints an error message if not
found. Returns `True` if available, `False` otherwise.

#### `_has_indicator() -> bool`

Check if the indicator service file is installed in the user systemd directory.
Returns `True` if `~/.config/systemd/user/forgewatch-indicator.service`
exists.

---

## `cli/uninstall.py` -- Uninstall command

Module: `forgewatch.cli.uninstall`

Uninstall flow that replaces the deprecated `uninstall.sh` script.

### `run_uninstall() -> None`

Entry point for the `forgewatch uninstall` command.

**Flow (5 steps):**

| Step | Description |
|---|---|
| 1 | **Stop indicator** -- stop (if active) and disable (if enabled) the indicator service |
| 2 | **Stop daemon** -- stop (if active) and disable (if enabled) the daemon service |
| 3 | **Remove service files** -- delete both `.service` files from `~/.config/systemd/user/`, run `daemon-reload`, remove legacy autostart entry |
| 4 | **Config cleanup** -- if config directory exists, prompt to remove it (default: no); uses `shutil.rmtree()` |
| 5 | **Summary** -- print completion message, config path if preserved, pip uninstall hint |

If `systemctl` is not available, steps 1-2 (stop/disable) are skipped, but
file removal in step 3 still proceeds.

### Internal helpers

#### `_stop_indicator() -> None`

Stop the indicator service if active, disable it if enabled.

#### `_stop_daemon() -> None`

Stop the daemon service if active, disable it if enabled.

#### `_remove_config() -> None`

Prompt the user to remove the config directory
(`~/.config/forgewatch/`). Default is `False` (keep). If the directory
does not exist, prints an info message and returns.

#### `_print_summary() -> None`

Print the final uninstall summary. If the config directory was preserved,
reminds the user of its location. Always prints the pip uninstall command.

---

## `cli/_output.py` -- Terminal output helpers

Module: `forgewatch.cli._output`

Coloured, structured output for CLI commands. Colour is suppressed when output
is not a TTY (piping, CI). Uses separate TTY detection for stdout and stderr
since `warn()` and `err()` write to stderr while other functions write to
stdout.

### Constants

| Constant | Value | Description |
|---|---|---|
| `_GREEN` | `\033[0;32m` | Green colour code |
| `_YELLOW` | `\033[1;33m` | Yellow (bold) colour code |
| `_RED` | `\033[0;31m` | Red colour code |
| `_BLUE` | `\033[0;34m` | Blue colour code |
| `_BOLD` | `\033[1m` | Bold text |
| `_RESET` | `\033[0m` | Reset all formatting |
| `_SUPPORTS_STDOUT_COLOR` | `sys.stdout.isatty()` | Whether stdout supports colour |
| `_SUPPORTS_STDERR_COLOR` | `sys.stderr.isatty()` | Whether stderr supports colour |

### `_fmt(code: str, text: str, *, stderr: bool = False) -> str`

Internal helper that wraps `text` in ANSI colour codes if the target stream
supports colour. Uses `_SUPPORTS_STDERR_COLOR` when `stderr=True`, otherwise
`_SUPPORTS_STDOUT_COLOR`.

### `info(msg: str) -> None`

Print an informational message to stdout with a blue `[INFO]` prefix.

### `ok(msg: str) -> None`

Print a success message to stdout with a green `[OK]` prefix.

### `warn(msg: str) -> None`

Print a warning message to stderr with a yellow `[WARN]` prefix.

### `err(msg: str) -> None`

Print an error message to stderr with a red `[ERR]` prefix.

### `step(num: int, total: int, msg: str) -> None`

Print a progress step message to stdout with a blue `[num/total]` prefix.

```python
step(1, 5, "Checking dependencies")
# Output: [1/5] Checking dependencies
```

---

## `cli/_prompts.py` -- Interactive prompt helpers

Module: `forgewatch.cli._prompts`

Helpers for the config wizard. Each function validates input and loops on
invalid values. All prompts handle `EOFError` gracefully (non-interactive
environments) by printing an error message and exiting with code 1.

### `_read_input(prompt: str) -> str`

Internal helper that wraps `builtins.input()`. Catches `EOFError` and exits
with a descriptive error message (handles non-interactive environments like
piped input or CI).

### `ask_string(prompt: str, *, default: str | None = None, required: bool = False) -> str`

Prompt for a string value.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | (required) | The prompt text |
| `default` | `str \| None` | `None` | Default value shown in `[brackets]` |
| `required` | `bool` | `False` | If `True`, loops until a non-empty value is entered |

Returns the entered string, or the default if the user presses Enter with an
empty input.

### `ask_yes_no(prompt: str, *, default: bool = True) -> bool`

Prompt for a yes/no answer.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | (required) | The prompt text |
| `default` | `bool` | `True` | Default when user presses Enter. Shown as `[Y/n]` or `[y/N]`. |

Accepts `y`, `yes`, `n`, `no` (case-insensitive). Loops on invalid input.

### `ask_int(prompt: str, *, default: int, minimum: int) -> int`

Prompt for an integer value.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | (required) | The prompt text |
| `default` | `int` | (required) | Default value shown in `[brackets]` |
| `minimum` | `int` | (required) | Minimum accepted value |

Validates that the input is a valid integer >= `minimum`. Loops on invalid
input (non-integer or below minimum).

### `ask_list(prompt: str, *, default: list[str] | None = None) -> list[str]`

Prompt for a comma-separated list of strings.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | (required) | The prompt text |
| `default` | `list[str] \| None` | `None` | Default value shown in `[brackets]` as comma-separated |

Splits input by commas, strips whitespace from each item, and filters out
empty strings.

---

## `cli/_checks.py` -- System dependency checks

Module: `forgewatch.cli._checks`

Check for optional system dependencies. Each function returns a `bool`
indicating whether the dependency is available, and prints an `[OK]` or
`[WARN]` message with installation hints.

### `check_notify_send() -> bool`

Check if `notify-send` is available on PATH via `shutil.which()`. Prints an
install hint (`sudo apt install libnotify-bin`) if not found.

### `check_dbus_session() -> bool`

Check if `DBUS_SESSION_BUS_ADDRESS` is set in the environment. Prints an
explanatory note (normal for SSH sessions) if not set.

### `check_gtk_indicator() -> bool`

Check if GTK3 and AppIndicator3 are importable. Attempts:

```python
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
```

Catches `ImportError` and `ValueError`. Prints install hints for system
packages if not available.

### `check_systemctl() -> bool`

Check if `systemctl` is available on PATH via `shutil.which()`.

---

## `cli/_systemd.py` -- Systemd operations

Module: `forgewatch.cli._systemd`

All systemd interactions in one module. Uses `subprocess.run()` with proper
error handling. Every function is a thin wrapper that can be easily mocked in
tests.

### Constants

| Constant | Value | Description |
|---|---|---|
| `SERVICE_DIR` | `Path.home() / ".config" / "systemd" / "user"` | User systemd unit directory |
| `DAEMON_SERVICE` | `"forgewatch.service"` | Daemon service file name |
| `INDICATOR_SERVICE` | `"forgewatch-indicator.service"` | Indicator service file name |
| `_LEGACY_AUTOSTART` | `Path.home() / ".config" / "autostart" / "forgewatch-indicator.desktop"` | Legacy XDG autostart file path |

### `_read_service_file(name: str) -> str`

Internal helper. Read a bundled service file from the `cli/systemd/` package
data directory via `importlib.resources.files("forgewatch.cli.systemd")`.

### `_run_systemctl(*args: str) -> subprocess.CompletedProcess[bytes]`

Internal helper. Run `systemctl --user <args>` with `check=False` and
`capture_output=True`. Returns the `CompletedProcess` result.

### `install_service_files(*, include_indicator: bool = False) -> None`

Copy bundled service files to the user systemd directory.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `include_indicator` | `bool` | `False` | Also install the indicator service file |

1. Creates `SERVICE_DIR` if needed (`mkdir -p`)
2. For each service being installed, checks if the file already exists and is
   enabled. If so, disables it first to remove stale `WantedBy=` symlinks.
3. Reads the daemon service file from package data and writes it to
   `SERVICE_DIR / DAEMON_SERVICE`
4. If `include_indicator`, also writes `INDICATOR_SERVICE`
5. Calls `daemon_reload()`
6. Re-enables any services that were previously enabled, creating fresh
   symlinks that match the new `WantedBy=` directive

The disable+re-enable cycle is necessary because `systemctl daemon-reload`
does not update existing enable symlinks when `WantedBy=` changes in the
service file.

### `remove_service_files() -> None`

Remove both service files (daemon and indicator) from `SERVICE_DIR` if they
exist. Calls `daemon_reload()` after removal.

### `daemon_reload() -> None`

Run `systemctl --user daemon-reload` to pick up unit file changes.

### `is_active(service: str) -> bool`

Check if a service is currently active (running). Returns `True` if
`systemctl --user is-active --quiet <service>` exits with code 0.

### `is_enabled(service: str) -> bool`

Check if a service is enabled for autostart. Returns `True` if
`systemctl --user is-enabled --quiet <service>` exits with code 0.

### `start(service: str) -> None`

Start a systemd user service. Prints `[OK]` or `[WARN]` based on the exit
code.

### `stop(service: str) -> None`

Stop a systemd user service. Prints `[OK]` or `[WARN]` based on the exit
code.

### `restart(service: str) -> None`

Restart a systemd user service. Prints `[OK]` or `[WARN]` based on the exit
code.

### `enable(service: str) -> None`

Enable a systemd user service for autostart. Prints `[OK]` or `[WARN]` based
on the exit code.

### `disable(service: str) -> None`

Disable a systemd user service from autostart. Prints `[OK]` or `[WARN]` based
on the exit code.

### `print_status(service: str) -> None`

Print the status of a systemd user service. Runs
`systemctl --user status <service> --no-pager` with output going directly to
the terminal (no capture).

### `service_file_installed(service: str) -> bool`

Check if a service file exists in the user systemd directory. Returns `True`
if `SERVICE_DIR / service` exists.

### `remove_legacy_autostart() -> None`

Remove the legacy XDG autostart desktop file
(`~/.config/autostart/forgewatch-indicator.desktop`) if it exists. This
cleans up entries created by older versions of the install script.

---

## Design notes

- **Mostly stdlib:** The CLI package uses the Python standard library
  (`argparse`, `subprocess`, `shutil`, `pathlib`, `importlib.resources`) for
  most subcommands. The `completions` subcommand uses `shtab` for
  shell-completion generation. This keeps the dependency footprint minimal
  and ensures the management commands work even if optional runtime
  dependencies (aiohttp, dbus-next) fail to import.
- **Lazy imports:** Subcommand modules (`setup.py`, `service.py`,
  `uninstall.py`) are imported lazily inside `run_cli()` to avoid loading
  unused code when only one subcommand is invoked. `shtab` is also imported
  lazily inside `dispatch()` and `build_full_parser()`.
- **Subcommand detection:** Happens in `__main__.py` via the unified argparse
  parser (`build_full_parser()`). When `args.command` is not `None`, the
  request is dispatched to `cli.dispatch(args)`. Otherwise the daemon starts.
  This avoids conflicts between daemon flags (`-c`, `-v`) and subcommand
  names.
- **Separate stdout/stderr TTY detection:** `_output.py` uses two separate
  `isatty()` checks because `warn()` and `err()` write to stderr (which may
  have different TTY status than stdout when piping).
- **Bundled service files:** The `.service` files live in `cli/systemd/` and
  are read via `importlib.resources`, which works correctly for both editable
  installs and PyPI packages.
- **Graceful degradation:** When `systemctl` is not available (e.g. in
  containers or macOS), service management steps are skipped but config
  creation and file operations still proceed.

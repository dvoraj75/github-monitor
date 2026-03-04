# Architecture

This document describes the high-level design of github-monitor, the
interactions between its components, and the rationale behind key decisions.

## Overview

github-monitor is a long-running Python daemon designed for a single purpose:
keep you informed about GitHub pull requests that need your attention. It runs as
a systemd user service, polls the GitHub API on a timer, diffs the results
against its in-memory state, sends desktop notifications for new PRs, and
exposes current state over D-Bus so that external tools (panel plugins, CLI
scripts) can query it.

## Component diagram

```
                      ┌────────────────────────────────────────────────────┐
                      │                    Daemon                         │
                      │                                                    │
 ┌──────────┐        │  ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
 │  GitHub   │◄───────│──│  Poller  │───►│  State   │───►│   Notifier   │  │
 │  REST API │        │  │          │    │  Store   │    │ (notify-send)│  │
 └──────────┘        │  └──────────┘    └────┬─────┘    └──────────────┘  │
                      │                      │                             │
                      │                 ┌────▼─────┐                      │
                      │                 │  D-Bus   │                      │
                      │                 │ Interface│                      │
                      │                 └────┬─────┘                      │
                      └──────────────────────┼────────────────────────────┘
                                             │
                                     D-Bus session bus
                                             │
                      ┌──────────────────────┼────────────────────────────┐
                      │                Indicator                          │
                      │                                                    │
                      │  ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
                      │  │  D-Bus   │───►│  Tray    │    │   Popup      │  │
                      │  │  Client  │    │  Icon    │    │   Window     │  │
                      │  └──────────┘    └──────────┘    └──────────────┘  │
                      └────────────────────────────────────────────────────┘
```

## Components

### Configuration (`config.py`)

Loads and validates a TOML configuration file. Supports three-tier path
resolution (explicit path > `GITHUB_MONITOR_CONFIG` env var > default XDG
path), environment variable overrides for the token, and strict validation of
all fields.

See [modules/config.md](modules/config.md) for the full API reference.

### Poller (`poller.py`)

An async HTTP client that queries the GitHub Search Issues API for open PRs
where the user is either a requested reviewer or an assignee. The API base URL
is configurable to support GitHub Enterprise Server installations. Handles
pagination (Link header), rate limiting (X-RateLimit headers with preemptive
waiting), retries with exponential backoff on 5xx errors (configurable retry
count), and proper error classification (401 -> `AuthError`, 403 -> rate limit
retry, network errors -> graceful degradation).

The two search queries are run concurrently via `asyncio.gather`, and results
are deduplicated by PR URL, with flags merged when a PR appears in both
queries.

See [modules/poller.md](modules/poller.md) for the full API reference.

### State Store (`store.py`)

Holds current PR state in an in-memory dictionary keyed by PR URL. On each
poll cycle, the store computes a diff: which PRs are new, which were updated,
and which have disappeared (closed/merged). This diff drives both notifications
and D-Bus signals. `StateDiff` and `StoreStatus` are frozen dataclasses
(immutable value objects).

See [modules/store.md](modules/store.md) for the full API reference.

### D-Bus Interface (`dbus_service.py`)

Exposes the daemon's state on the session bus under the well-known name
`org.github_monitor.Daemon` at object path `/org/github_monitor/Daemon`.
Provides three methods (`GetPullRequests`, `GetStatus`, `Refresh`) and one
signal (`PullRequestsChanged`). All data is serialised as JSON strings over
the D-Bus wire format.

The `Refresh` method is async — it triggers an immediate poll cycle and
returns the updated PR list. The `PullRequestsChanged` signal is emitted by
the daemon after each poll cycle that produces changes, carrying the full
current PR list as its payload. This is the integration point for future panel
plugins or CLI tools.

See [modules/dbus_service.md](modules/dbus_service.md) for the full API reference.

### Notifier (`notifier.py`)

Sends desktop notifications via `notify-send` (subprocess call). For small
batches (<= configurable threshold, default 3), each PR gets its own
notification with the author's avatar as the icon and a clickable "Open" action
that opens the PR in the default browser via the XDG Desktop Portal (D-Bus),
falling back to `xdg-open` when the portal is unavailable. The portal approach
is used because `xdg-open` fails silently inside the systemd sandbox when the
browser is a Snap package. For larger batches, a single summary notification is
sent. Avatars are downloaded from GitHub and
cached on disk. A shared `aiohttp.ClientSession` is reused for all avatar
downloads within a notification batch.

See [modules/notifier.md](modules/notifier.md) for the full API reference.

### URL Opener (`url_opener.py`)

A shared utility module used by both the notifier and the indicator to open URLs
in the default browser. It tries the XDG Desktop Portal (D-Bus) first, which
works correctly from sandboxed systemd services, Flatpak, and Snap environments.
If the portal is unavailable, it falls back to `xdg-open`. This module was
extracted from the notifier to avoid code duplication once the indicator also
needed URL-opening capabilities.

See [modules/url_opener.md](modules/url_opener.md) for the full API reference.

### Indicator (`indicator/`)

An optional separate process that provides a system tray icon with a live PR
count and a clickable popup window. The indicator connects to the daemon over
D-Bus and is architecturally independent -- it does not import any daemon
modules. It consists of:

- **Entry point** (`__main__.py`) -- checks for GTK3, AppIndicator3, and gbulb
  dependencies before importing any indicator code. Loads `config.toml`
  (best-effort) to read the `icon_theme` setting, falling back to `"light"` if
  config loading fails. Installs the gbulb event loop (GLib + asyncio
  integration) and launches the application.
- **Orchestrator** (`app.py`) -- wires the D-Bus client, tray icon, and popup
  window. Bridges synchronous GTK callbacks and asynchronous D-Bus calls.
- **D-Bus client** (`client.py`) -- connects to the daemon's
  `org.github_monitor.Daemon` bus name, subscribes to the
  `PullRequestsChanged` signal for live updates, and auto-reconnects when the
  daemon disappears.
- **Tray icon** (`tray.py`) -- AppIndicator3-based system tray icon with a PR
  count label and colour-coded icons (neutral, active, alert, disconnected).
  Icons are loaded from `resources/light/` or `resources/dark/` depending on
  the configured `icon_theme`, allowing proper visibility on both light and
  dark desktop panels. Provides a GTK menu with Show/Hide PRs, Refresh, and
  Quit actions.
- **Popup window** (`window.py`) -- GTK3 window positioned near the tray icon
  showing a scrollable list of PRs. Each row displays the repo, PR number,
  title, author, and relative time. Clicking a row opens the PR in the browser
  via the shared `url_opener` module.
- **Models** (`models.py`) -- `PRInfo` and `DaemonStatus` frozen dataclasses
  for data received from the daemon. These are intentionally separate from the
  daemon's `PullRequest` dataclass to maintain process boundary isolation.
- **Pure helpers** (`_tray_state.py`, `_window_helpers.py`) -- stateless
  functions for icon selection, label formatting, relative time, PR sorting,
  and Pango markup escaping. These have zero GTK imports and are fully
  unit-testable without system packages.

See [modules/indicator.md](modules/indicator.md) for the full API reference.

### CLI Management (`cli/`)

A management interface providing `setup`, `service`, and `uninstall`
subcommands for installing and managing github-monitor as a systemd user
service. Uses stdlib only (no extra dependencies beyond the Python standard
library). The package consists of:

- **Parser and dispatch** (`__init__.py`) -- argparse subcommand parser with
  lazy imports to avoid loading unused code.
- **Setup wizard** (`setup.py`) -- interactive configuration (token, username,
  poll interval, repos), systemd service installation, and enable + start.
  Supports `--config-only` and `--service-only` flags.
- **Service management** (`service.py`) -- thin CLI layer over systemd
  operations. Wraps install, start, stop, restart, status, enable, and disable.
  Automatically manages the indicator service when its unit file is installed.
- **Uninstall** (`uninstall.py`) -- stops and disables services, removes
  systemd unit files and the legacy autostart entry, optionally removes the
  config directory.
- **Shared helpers** (`_output.py`, `_prompts.py`, `_checks.py`, `_systemd.py`)
  -- coloured terminal output, interactive prompts with validation, system
  dependency checks (notify-send, D-Bus, GTK, systemctl), and all systemd
  interactions via `subprocess.run()`.
- **Bundled service files** (`systemd/`) -- `.service` files accessed via
  `importlib.resources`, allowing installation from PyPI packages without a git
  checkout.

Subcommand detection happens in `__main__.py` by checking `sys.argv[1]`
against a known set of command names before the daemon argparse runs, ensuring
full backward compatibility with existing daemon flags (`-c`, `-v`).

See [modules/cli.md](modules/cli.md) for the full API reference.

### Daemon (`daemon.py`)

The main orchestrator. Wires together all components: loads config, starts the
poller, runs poll cycles on a timer, feeds results into the state store, triggers
notifications and D-Bus signals on diffs, and handles Unix signals (SIGTERM /
SIGINT for shutdown, SIGHUP for config reload).

The poll loop uses `asyncio.wait()` with two event tasks (shutdown and reload)
instead of `asyncio.sleep` so that both shutdown and config reload are immediate
rather than waiting for the current sleep to finish. First-poll notifications are
suppressed by default to avoid notification spam on startup (configurable via
`notify_on_first_poll`). The D-Bus signal still fires so panel plugins can
populate state. D-Bus setup is conditional on `dbus_enabled`, allowing the daemon
to run in environments where D-Bus is unavailable. On SIGHUP, the daemon reloads
the config file (respecting the original `-c` path), applies the new log level
immediately, restarts the HTTP session to pick up new token/headers, and wakes
the poll loop for an immediate re-poll with the new configuration.

See [modules/daemon.md](modules/daemon.md) for the full API reference.

## Data flow

### Poll cycle (daemon)

A single poll cycle follows this path:

```
1. Timer fires (every poll_interval seconds)
2. Poller.fetch_all()
   ├── fetch_review_requested()  ──► GitHub Search API (paginated)
   └── fetch_assigned()          ──► GitHub Search API (paginated)
   └── Deduplicate + merge flags
3. State Store.update(prs)
   ├── Compute diff (new, updated, closed)
   └── Replace internal state
4. If diff has new PRs (and notifications enabled):
   └── Notifier.notify_new_prs(diff.new, threshold=..., urgency=...)
5. If diff is non-empty:
   └── D-Bus signal: PullRequestsChanged
```

### D-Bus to indicator

When the indicator is running, it receives live updates from the daemon over
the session bus:

```
1. Daemon emits PullRequestsChanged signal (JSON payload)
        │
        ▼
2. DaemonClient._on_signal() receives the JSON string
   └── _parse_prs() deserialises JSON → list[PRInfo]
        │
        ▼
3. IndicatorApp._on_prs_changed() (synchronous callback)
   └── Schedules _handle_prs_changed() as an async task
        │
        ▼
4. _handle_prs_changed()
   ├── DaemonClient.get_status() → DaemonStatus (pr_count, last_updated)
   └── _update_ui(prs, status)
        ├── TrayIcon.set_pr_count()     → update label + icon colour
        └── PRWindow.update_prs()       → rebuild scrollable PR list + footer
```

On-demand refresh follows a similar path: the user clicks "Refresh" in the
tray menu or popup window, the indicator calls the daemon's `Refresh()` D-Bus
method, receives the updated PR list, and updates the UI.

## Key design decisions

### Why the Search API instead of listing endpoints?

The GitHub REST API offers both repository-level PR listing (`GET
/repos/{owner}/{repo}/pulls`) and the Search Issues endpoint (`GET
/search/issues`). We use the search endpoint because:

- It can query across all repositories in a single request (no need to
  enumerate repos)
- It supports filtering by `review-requested:{user}` and `assignee:{user}`
  directly in the query
- It respects the user's configured repo filter when provided

The tradeoff is a tighter rate limit on the search endpoint (30 req/min
authenticated vs 5000 req/hour for REST), but with a 5-minute default poll
interval and two queries per cycle, this is not a practical concern.

### Why in-memory state instead of SQLite?

For a v1 PoC, in-memory state is simpler and sufficient. The daemon only needs
to know "what PRs are currently open and assigned to me" — there is no history
or persistence requirement. If the daemon restarts, it re-fetches from GitHub
on the first poll cycle. A future version could add SQLite for history and
analytics.

### Why D-Bus?

D-Bus is the standard IPC mechanism on Linux desktops. It allows future panel
plugins (XFCE, GNOME, etc.) and CLI tools to query daemon state without the
overhead of a web server or socket protocol. The `dbus-next` library provides a
clean async Python interface.

### Why asyncio?

All I/O in this daemon is either network (GitHub API) or IPC (D-Bus). asyncio
is the natural fit: `aiohttp` for HTTP, `dbus-next` for D-Bus, and
`asyncio.wait` for the poll timer (with event-based wake). There are no CPU-bound tasks.

### Why `dataclass + tomllib` instead of pydantic?

For a small project with a dozen config fields and a handful of data classes, stdlib
`dataclass` + `tomllib` keeps the dependency footprint minimal. `pydantic` or
`pydantic-settings` could replace this in a future version if the config
grows more complex.

### Tight coupling in the poller

The poller is currently PR-specific — it knows about GitHub search queries,
PR field mapping, and the `PullRequest` dataclass. A more generic approach
would define a `Source` protocol and a `GitHubItem` base type, allowing the
poller to fetch different kinds of GitHub data (issues, CI runs, etc.). This
refactoring is deferred to a future version; the current approach is
pragmatic for a PR-only PoC.

## Error handling strategy

The system is designed to be resilient to transient failures:

| Error | Behavior |
|---|---|
| Network error | Retry up to `max_retries` times (configurable, default 3) with exponential backoff, then return empty |
| HTTP 5xx | Retry up to `max_retries` times (configurable, default 3) with exponential backoff, then return empty |
| HTTP 401 | Raise `AuthError` immediately (bad token, no point retrying) |
| HTTP 403 | Respect `Retry-After` header, retry once, then return empty |
| Rate limit exhausted | Preemptively wait until reset time before making request |
| Invalid config | Raise `ConfigError` at startup (fail fast) |

The daemon should never crash from a transient GitHub API issue. It logs the
error and continues with the next poll cycle.

## Signal handling

| Signal | Behavior |
|---|---|
| `SIGTERM` / `SIGINT` | Graceful shutdown: set stop event, close HTTP session, unexport D-Bus, exit |
| `SIGHUP` | Reload configuration from disk, restart HTTP session, update poller settings, wake poll loop for immediate re-poll |

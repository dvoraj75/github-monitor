# github-monitor

![CI](https://github.com/dvoraj75/github-monitor/actions/workflows/ci.yml/badge.svg) ![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000) ![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue) ![Async](https://img.shields.io/badge/async-asyncio-purple)

A Python daemon that polls GitHub for pull requests assigned to you (as reviewer
or assignee), holds state in memory, exposes it over D-Bus, and sends desktop
notifications when new PRs arrive.

## Features

- **Live PR monitoring** -- polls GitHub Search API for PRs assigned to you or requesting your review
- **Desktop notifications** -- individual notifications for small batches with author avatars and clickable links; summary for larger batches (configurable threshold)
- **System tray indicator** -- optional panel icon with live PR count, colour-coded status, and a popup window listing all PRs (click to open in browser)
- **D-Bus interface** -- query current PR state, trigger manual refresh, subscribe to change signals (can be disabled)
- **GitHub Enterprise support** -- configurable API base URL
- **Systemd integration** -- runs as a user service with security hardening and `systemctl reload` support; optional companion service for the indicator
- **Resilient** -- exponential backoff with configurable retries, rate limit handling, graceful shutdown via signals (SIGTERM, SIGHUP for config reload)
- **Runtime configurable** -- log level, notification behaviour, D-Bus toggle, and more can be changed via config reload

![Notification screenshot](docs/screenshot.png)

## Architecture

```
┌──────────────┐         ┌─────────────────┐
│  GitHub API  │◄────────│  Poller         │
│  (REST)      │         │  (asyncio +     │
└──────────────┘         │   aiohttp)      │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  State Store    │
                         │  (in-memory     │
                         │   dict)         │
                         └───┬─────────┬───┘
                             │         │
                    ┌────────▼──┐  ┌───▼──────────┐
                    │ Notifier  │  │ D-Bus        │
                    │ (notify-  │  │ Interface    │
                    │  send)    │  │              │
                    └───────────┘  └───┬──────────┘
                                       │
                               D-Bus session bus
                                       │
                               ┌───────▼────────┐
                               │   Indicator    │
                               │  (system tray  │
                               │   + popup)     │
                               └────────────────┘
The poller queries the GitHub Search API on a configurable interval, the state
store computes diffs (new / updated / closed PRs), the notifier sends desktop
notifications for new PRs, and the D-Bus interface lets external tools query
current state. The system tray indicator is a separate process that connects
to the daemon over D-Bus to display a live PR count and a clickable popup.

For a deeper dive, see [docs/architecture.md](docs/architecture.md).

## Quick start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- `notify-send` (usually part of `libnotify` — for desktop notifications)
- A GitHub personal access token with `repo` scope

### Install

```bash
git clone https://github.com/dvoraj75/github-monitor.git
cd github-monitor
uv sync            # installs runtime + dev dependencies
```

### Configure

Copy the example config and fill in your details:

```bash
mkdir -p ~/.config/github-monitor
cp config.example.toml ~/.config/github-monitor/config.toml
$EDITOR ~/.config/github-monitor/config.toml
```

```toml
github_token    = "ghp_your_personal_access_token"
github_username = "your-github-username"
poll_interval   = 300       # seconds (minimum 30)
repos           = []        # empty = all repos, or ["owner/repo1", "owner/repo2"]

# Optional settings (shown with defaults):
# log_level              = "info"       # debug, info, warning, error
# notifications_enabled  = true         # toggle desktop notifications
# dbus_enabled           = true         # toggle D-Bus interface
# github_base_url        = "https://api.github.com"  # for GitHub Enterprise
# max_retries            = 3            # HTTP retries for 5xx errors
# notification_threshold = 3            # individual vs. summary cutoff
# notification_urgency   = "normal"     # low, normal, critical
```

The token can also be provided via the `GITHUB_TOKEN` environment variable,
which takes precedence over the config file value.

See [docs/configuration.md](docs/configuration.md) for the full reference.

### Run

```bash
# Direct execution
uv run github-monitor

# Or via python -m
uv run python -m github_monitor
```

Command-line flags:

```bash
# Custom config path
uv run github-monitor -c /path/to/config.toml

# Verbose logging (DEBUG level)
uv run github-monitor -v
```

### Run the indicator (optional)

The system tray indicator is a separate process that connects to the running
daemon over D-Bus. It requires GTK3 and AppIndicator3 system packages (see
[Dependencies](#system-tray-indicator-optional) below).

```bash
# Start the indicator (daemon must be running)
uv run github-monitor-indicator

# Or via python -m
uv run python -m github_monitor.indicator

# Verbose logging
uv run github-monitor-indicator -v
```

### Automated install / update / uninstall

The project includes scripts for managing github-monitor as a systemd user
service:

```bash
./install.sh     # interactive install (prereqs, package, config, systemd service)
./update.sh      # pull latest + re-install package + restart service
./uninstall.sh   # stop service, remove package, optionally remove config
```

The install script is interactive and walks you through configuration.
The update script is git-aware -- it will skip `git pull` if you have
uncommitted changes or are on a non-main branch (unless you confirm).

### Systemd user service (manual setup)

If you prefer to set things up manually instead of using the install script:

```bash
# Install the daemon service
mkdir -p ~/.config/systemd/user/
cp systemd/github-monitor.service ~/.config/systemd/user/

# Enable and start
systemctl --user daemon-reload
systemctl --user enable --now github-monitor

# Check logs
journalctl --user -u github-monitor -f
```

To also run the system tray indicator as a service:

```bash
cp systemd/github-monitor-indicator.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now github-monitor-indicator
```

The indicator service depends on the daemon -- systemd starts them in the
correct order and the indicator auto-reconnects if the daemon restarts.

See [docs/systemd.md](docs/systemd.md) for the full guide, including token
configuration, security hardening details, and troubleshooting.

## Project structure

```
github-monitor/
├── config.example.toml          # Example configuration file
├── pyproject.toml               # Project metadata, deps, tool config
├── install.sh                   # Automated installer script
├── update.sh                    # Update script (pull + reinstall + restart)
├── uninstall.sh                 # Uninstall script
│
├── github_monitor/
│   ├── __init__.py              # Package marker (__version__)
│   ├── __main__.py              # python -m github_monitor entry point
│   ├── config.py                # Configuration loading and validation
│   ├── poller.py                # GitHub API client (search, pagination, rate limits)
│   ├── store.py                 # In-memory state store with diff computation
│   ├── dbus_service.py          # D-Bus interface (methods, signals, bus setup)
│   ├── notifier.py              # Desktop notifications via notify-send
│   ├── url_opener.py            # Shared URL opener (XDG portal + xdg-open fallback)
│   ├── daemon.py                # Main daemon loop and signal handling
│   │
│   └── indicator/               # System tray indicator (optional, separate process)
│       ├── __init__.py
│       ├── __main__.py          # python -m github_monitor.indicator entry point
│       ├── app.py               # Application orchestrator
│       ├── client.py            # D-Bus client for daemon communication
│       ├── tray.py              # System tray icon (AppIndicator3)
│       ├── window.py            # Popup window (GTK3) with PR list
│       ├── models.py            # PRInfo and DaemonStatus dataclasses
│       ├── _tray_state.py       # Pure icon/label state logic (no GTK imports)
│       ├── _window_helpers.py   # Pure helpers: relative time, sorting, markup
│       └── resources/           # SVG icons for the tray indicator
│
├── systemd/
│   ├── github-monitor.service           # Systemd user service (daemon)
│   └── github-monitor-indicator.service # Systemd user service (indicator)
│
├── tests/
│   ├── test_config.py           # Tests for config module
│   ├── test_poller.py           # Tests for poller module
│   ├── test_store.py            # Tests for store module
│   ├── test_dbus_service.py     # Tests for D-Bus service module
│   ├── test_notifier.py         # Tests for notifier module
│   ├── test_daemon.py           # Tests for daemon module
│   ├── test_main.py             # Tests for __main__ module
│   ├── test_indicator_app.py    # Tests for indicator app orchestrator
│   ├── test_indicator_client.py # Tests for indicator D-Bus client
│   ├── test_indicator_tray.py   # Tests for indicator tray state logic
│   └── test_indicator_window.py # Tests for indicator window helpers
│
└── docs/                        # Detailed documentation
    ├── architecture.md
    ├── configuration.md
    ├── development.md
    ├── systemd.md
    └── modules/
        ├── config.md
        ├── poller.md
        ├── store.md
        ├── dbus_service.md
        ├── notifier.md
        ├── url_opener.md
        ├── daemon.md
        └── indicator.md
```

## Development

```bash
uv sync                        # install all deps (runtime + dev group)
uv run pytest                  # run tests (ALL passing)
uv run ruff check .            # lint (ALL rules enabled)
uv run ruff format .           # format (black-compatible)
uv run mypy .                  # type check (strict mode)
```

See [docs/development.md](docs/development.md) for coding conventions, tooling
details, and project structure notes.

## Documentation

| Document | Description |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System design, component interactions, design decisions |
| [docs/configuration.md](docs/configuration.md) | Full configuration reference with examples |
| [docs/development.md](docs/development.md) | Developer guide: tooling, conventions, testing |
| [docs/systemd.md](docs/systemd.md) | Systemd user service setup and management |
| [docs/modules/config.md](docs/modules/config.md) | `config.py` API reference |
| [docs/modules/poller.md](docs/modules/poller.md) | `poller.py` API reference |
| [docs/modules/store.md](docs/modules/store.md) | `store.py` API reference |
| [docs/modules/dbus_service.md](docs/modules/dbus_service.md) | `dbus_service.py` API reference |
| [docs/modules/notifier.md](docs/modules/notifier.md) | `notifier.py` API reference |
| [docs/modules/url_opener.md](docs/modules/url_opener.md) | `url_opener.py` API reference |
| [docs/modules/daemon.md](docs/modules/daemon.md) | `daemon.py` API reference |
| [docs/modules/indicator.md](docs/modules/indicator.md) | Indicator package API reference |

## Dependencies

| Package | Purpose |
|---|---|
| `aiohttp` | Async HTTP client for GitHub API |
| `dbus-next` | Async D-Bus client/server |
| `tomllib` (stdlib) | TOML config parsing |
| `notify-send` (system) | Desktop notifications |

Dev-only: `pytest`, `pytest-asyncio`, `pytest-xdist`, `pytest-cov`,
`aioresponses`, `ruff`, `mypy`, `pre-commit`.

### System tray indicator (optional)

The indicator is a separate process that shows a tray icon with live PR
count. It connects to the daemon over D-Bus and requires additional
dependencies:

**Python packages** (installed automatically with `--extra indicator`):

| Package | Purpose |
|---|---|
| `gbulb` | GLib/asyncio event loop integration |

**System packages** (must be installed manually via your package manager):

```bash
# Ubuntu / Debian
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    gir1.2-appindicator3-0.1 libcairo2-dev libgirepository1.0-dev

# Fedora
sudo dnf install python3-gobject gtk3 libappindicator-gtk3
```

Then install with indicator support:

```bash
uv sync --extra indicator
```

The core daemon works without any of these — the indicator is fully optional.

## License

MIT — see [LICENSE](LICENSE) for details.

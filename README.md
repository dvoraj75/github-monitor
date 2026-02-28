# github-monitor

A Python daemon that polls GitHub for pull requests assigned to you (as reviewer
or assignee), holds state in memory, exposes it over D-Bus, and sends desktop
notifications when new PRs arrive.

> **Status:** Work in progress. Phases 1-6 (scaffold, configuration, poller,
> state store, D-Bus service, notifier) are complete with full test coverage.
> Phases 7-8 (daemon, systemd) are not yet implemented.

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
                                      ▼
                              D-Bus session bus
                                      │
                              ┌───────▼────────┐
                              │ Future: Panel  │
                              │ Plugin / CLI   │
                              └────────────────┘
```

The poller queries the GitHub Search API on a configurable interval, the state
store computes diffs (new / updated / closed PRs), the notifier sends desktop
notifications for new PRs, and the D-Bus interface lets external tools query
current state.

For a deeper dive, see [docs/architecture.md](docs/architecture.md).

## Quick start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- `notify-send` (usually part of `libnotify` — for desktop notifications)
- A GitHub personal access token with `repo` scope

### Install

```bash
git clone https://github.com/<you>/github-monitor.git
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

> **Note:** The daemon entry point is a stub until Phase 7 is implemented. The
> configuration, poller, state store, D-Bus service, and notifier modules are
> fully functional and can be used programmatically.

## Project structure

```
github-monitor/
├── config.example.toml          # Example configuration file
├── pyproject.toml               # Project metadata, deps, tool config
├── plan.md                      # Architecture design document
├── implementation.md            # Step-by-step implementation guide
│
├── github_monitor/
│   ├── __init__.py              # Package marker (__version__)
│   ├── __main__.py              # python -m github_monitor entry point
│   ├── config.py                # Configuration loading and validation
│   ├── poller.py                # GitHub API client (search, pagination, rate limits)
│   ├── store.py                 # In-memory state store with diff computation
│   ├── dbus_service.py          # D-Bus interface (methods, signals, bus setup)
│   ├── notifier.py              # Desktop notifications via notify-send
│   └── daemon.py                # Main daemon loop (not yet implemented)
│
├── tests/
│   ├── test_config.py           # 17 tests for config module
│   ├── test_poller.py           # 21 tests for poller module
│   ├── test_store.py            # 24 tests for store module
│   ├── test_dbus_service.py     # 28 tests for D-Bus service module
│   └── test_notifier.py         # 24 tests for notifier module
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
        └── daemon.md
```

## Development

```bash
uv sync                        # install all deps (runtime + dev group)
uv run pytest                  # run tests (114 passing)
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
| [docs/systemd.md](docs/systemd.md) | Systemd user service setup (planned) |
| [docs/modules/config.md](docs/modules/config.md) | `config.py` API reference |
| [docs/modules/poller.md](docs/modules/poller.md) | `poller.py` API reference |
| [docs/modules/store.md](docs/modules/store.md) | `store.py` API reference |
| [docs/modules/dbus_service.md](docs/modules/dbus_service.md) | `dbus_service.py` API reference |
| [docs/modules/notifier.md](docs/modules/notifier.md) | `notifier.py` API reference |
| [docs/modules/daemon.md](docs/modules/daemon.md) | `daemon.py` API reference (planned) |

## Implementation phases

| Phase | Module | Status |
|---|---|---|
| 1. Scaffold | pyproject.toml, package structure | Done |
| 2. Configuration | `config.py` | Done |
| 3. GitHub Poller | `poller.py` | Done |
| 4. State Store | `store.py` | Done |
| 5. D-Bus Service | `dbus_service.py` | Done |
| 6. Notifier | `notifier.py` | Done |
| 7. Daemon | `daemon.py`, `__main__.py` | Not started |
| 8. Systemd | `github-monitor.service` | Not started |

## Dependencies

| Package | Purpose |
|---|---|
| `aiohttp` | Async HTTP client for GitHub API |
| `dbus-next` | Async D-Bus client/server |
| `tomllib` (stdlib) | TOML config parsing |
| `notify-send` (system) | Desktop notifications |

Dev-only: `pytest`, `pytest-asyncio`, `aioresponses`, `ruff`, `mypy`.

## License

TBD

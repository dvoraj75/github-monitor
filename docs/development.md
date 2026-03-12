# Development guide

This document covers the development setup, tooling configuration, coding
conventions, and testing approach for ForgeWatch.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended package manager)

## Setup

```bash
git clone https://github.com/dvoraj75/forgewatch.git
cd forgewatch
uv sync          # installs runtime deps + dev dependency group
```

This installs the project in editable mode along with all dev tools (pytest,
ruff, mypy, etc.).

## Project structure

```
forgewatch/              # Main package
├── __init__.py          # __version__ (from package metadata)
├── __main__.py          # Entry point -- dispatches to CLI subcommands or daemon
├── config.py            # Config loading + validation
├── poller.py            # GitHub API client
├── store.py             # State store
├── dbus_service.py      # D-Bus interface
├── notifier.py          # Desktop notifications
├── url_opener.py        # Shared URL opener (XDG portal + xdg-open)
├── daemon.py            # Main daemon loop
├── cli/                 # CLI management subcommands (stdlib only)
│   ├── __init__.py      # Subcommand parser + dispatch
│   ├── setup.py         # Setup wizard (config + systemd)
│   ├── service.py       # Service management (start/stop/status/...)
│   ├── uninstall.py     # Uninstall flow (stop, remove, cleanup)
│   ├── _output.py       # Coloured terminal output helpers
│   ├── _prompts.py      # Interactive prompt helpers
│   ├── _checks.py       # System dependency checks
│   ├── _systemd.py      # Systemd operations (install/remove/start/stop)
│   └── systemd/         # Bundled .service files (importlib.resources)
└── indicator/           # System tray indicator (separate process)
    ├── __init__.py
    ├── __main__.py      # Entry point + dependency checks
    ├── app.py           # Orchestrator (D-Bus client + tray + window)
    ├── client.py        # D-Bus client for daemon communication
    ├── tray.py          # AppIndicator3 system tray icon
    ├── window.py        # GTK3 popup window with PR list
    ├── models.py        # PRInfo + DaemonStatus dataclasses
    ├── _tray_state.py   # Pure icon/label/tooltip logic (no GTK imports)
    ├── _window_helpers.py  # Pure helpers (relative time, sorting, escaping)
    └── resources/       # Tray icon image files

systemd/
├── forgewatch.service            # Systemd user service (daemon)
└── forgewatch-indicator.service  # Systemd user service (indicator)

tests/
├── conftest.py          # Shared test fixtures
├── test_config.py       # Config loading and validation
├── test_poller.py       # GitHub API client
├── test_store.py        # State store and diffing
├── test_dbus_service.py # D-Bus interface
├── test_notifier.py     # Desktop notifications
├── test_daemon.py       # Daemon lifecycle and integration
├── test_main.py         # CLI entry point
├── test_url_opener.py       # URL opener (XDG portal + xdg-open)
├── test_indicator_app.py    # Indicator orchestrator
├── test_indicator_client.py # Indicator D-Bus client
├── test_indicator_tray.py   # Indicator tray icon
├── test_indicator_window.py # Indicator popup window + helpers
├── test_indicator_main.py   # Indicator entry point
├── test_cli_init.py         # CLI parser + dispatch
├── test_cli_output.py       # CLI output helpers
├── test_cli_prompts.py      # CLI prompt helpers
├── test_cli_checks.py       # CLI dependency checks
├── test_cli_systemd.py      # CLI systemd operations
├── test_cli_setup.py        # CLI setup command
├── test_cli_service.py      # CLI service command
└── test_cli_uninstall.py    # CLI uninstall command
```

## Running checks

All checks should pass before merging:

```bash
# Lint (ruff with ALL rules)
uv run ruff check .

# Format (ruff as black replacement)
uv run ruff format .

# Type check (mypy strict)
uv run mypy .

# Tests
uv run pytest            # all tests, parallel with coverage
uv run pytest -v         # verbose output
uv run pytest -x         # stop on first failure
```

Run everything in one shot:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

## Tooling configuration

All tool configuration lives in `pyproject.toml`. There are no separate
`.ruff.toml`, `mypy.ini`, or `pytest.ini` files.

### Ruff

```toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["ALL"]
ignore = [
    "D",       # pydocstyle — skip docstring enforcement for now
    "ANN",     # flake8-annotations — mypy strict handles this better
    "COM812",  # trailing comma — conflicts with ruff formatter
    "ISC001",  # implicit string concat — conflicts with ruff formatter
]
```

We use `select = ["ALL"]` to enable every available rule, then ignore specific
rules that conflict with the formatter or are redundant with mypy. This is the
strictest possible ruff configuration.

Test files get relaxed rules:

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
    "S101",    # assert usage is fine in tests
    "S105",    # hardcoded passwords are test fixtures
    "S106",    # hardcoded passwords in function args
    "S108",    # hardcoded temp file paths are fine in tests
    "PLR2004", # magic values are fine in tests
    "PLC0415", # imports inside test functions for cache access
    "SLF001",  # private member access is fine in tests
    "INP001",  # tests don't need __init__.py
    "ARG001",  # unused callback args (aioresponses callbacks)
    "ARG002",  # unused method args from stacked @patch decorators
    "PLR0913", # test helpers often mirror dataclass constructors
    "ERA001",  # commented-out code used as section headers in tests
]
"forgewatch/cli/_systemd.py" = [
    "S603",    # subprocess call with non-literal args — all args are internal constants
    "S607",    # partial executable path — systemctl is a standard system binary
]
```

### mypy

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
```

`strict = true` enables all optional strictness flags, including
`disallow_untyped_defs`, `disallow_any_generics`, `check_untyped_defs`, etc.
Every function must have complete type annotations.

### pytest

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-ra -v --cov=forgewatch --cov-report=term --cov-fail-under=90 -n auto"
```

`asyncio_mode = "auto"` means async test functions are automatically detected
and run in an event loop -- no need for `@pytest.mark.asyncio` decorators.

Tests run in parallel via `pytest-xdist` (`-n auto`) with coverage reporting
via `pytest-cov` (`--cov=forgewatch`). The `--cov-fail-under=90` flag
enforces a minimum 90% test coverage -- pytest will exit with a non-zero code
if total coverage drops below this threshold.

## Build system

The project uses [hatchling](https://hatch.pypa.io/) as its build backend:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Hatchling is required so that `uv` treats the project as an installable package,
which is needed for `from forgewatch import ...` to work in tests.

## Dependencies

Dependencies are managed in `pyproject.toml`:

```toml
[project]
dependencies = [
    "aiohttp>=3.9,<4",
    "dbus-next>=0.2.3,<1",
    "gbulb>=0.6",
]

[dependency-groups]      # PEP 735 — used by uv
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "aioresponses>=0.7",
    "ruff>=0.8",
    "mypy>=1.13",
    "pytest-xdist>=3.8.0",
    "pytest-cov>=7.0.0",
    "pre-commit>=4.5.1",
    "pip-audit>=2.7",
]
```

Dev dependencies use `[dependency-groups]` (PEP 735) rather than
`[project.optional-dependencies]` because the project uses `uv` as its package
manager. All runtime dependencies (including `gbulb` for the indicator) are in
core `[project.dependencies]` so a plain `pip install forgewatch` gets
everything needed.

### System tray indicator dependencies

The indicator (`forgewatch.indicator`) is optional and requires both Python
packages and system-level GTK3/AppIndicator3 libraries.

**System packages** (not installable via pip/uv):

```bash
# Ubuntu / Debian
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    gir1.2-appindicator3-0.1 libcairo2-dev libgirepository1.0-dev

# Fedora
sudo dnf install python3-gobject gtk3 libappindicator-gtk3
```

`gbulb` (GLib/asyncio event loop integration) is a core dependency and is
installed automatically with `pip install forgewatch` or `uv sync`. The C build
dependencies (`libcairo2-dev`, `libgirepository1.0-dev`) must be installed
first or the build will fail.

Without these, the core daemon works normally — only the system tray indicator
is unavailable. Running `python -m forgewatch.indicator` will print a clear
error message listing the missing packages.

## Coding conventions

### Type annotations

Every function must have complete type annotations (enforced by
`mypy --strict`). Use `from __future__ import annotations` at the top of every
file for PEP 604 union syntax (`X | Y`) and forward references.

For imports used only in type annotations, use the `TYPE_CHECKING` pattern:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
```

### Error handling

- Define specific exception classes (e.g., `ConfigError`, `AuthError`) rather
  than using generic `ValueError` or `RuntimeError`
- Build error messages in a local `msg` variable before raising (this satisfies
  ruff's `TRY003` and `EM101` rules about exception string formatting)

```python
# Good
msg = f"poll_interval must be >= {minimum}, got {value}"
raise ConfigError(msg)

# Bad — ruff will flag this
raise ConfigError(f"poll_interval must be >= {minimum}, got {value}")
```

### Dataclasses

- Use `@dataclass(frozen=True)` for value objects that should be immutable
  (e.g., `PullRequest`, `Config`)
- Use `@dataclass` (mutable) for objects with internal state (e.g., `PRStore`)
- Use `field(default_factory=list)` for mutable defaults

### Async patterns

- Use `aiohttp.ClientSession` for HTTP; create it once in `start()`, close in
  `close()`
- Use `asyncio.gather()` for concurrent operations (e.g., running both search
  queries)
- Use `asyncio.sleep()` for simple waits (e.g., rate limit backoff)
- The poll interval uses `asyncio.wait()` with event tasks for immediate
  wake on shutdown or config reload

## Testing

Tests live in the `tests/` directory. The test runner is pytest with
pytest-asyncio.

### Mocking HTTP

HTTP requests are mocked using `aioresponses`. Key patterns:

```python
import re
from aioresponses import CallbackResult, aioresponses

URL_RE = re.compile(r"^https://api\.github\.com/search/issues\b")

async def test_example() -> None:
    with aioresponses() as m:
        m.get(URL_RE, payload={"items": []})
        # ... make request ...
```

Use `re.compile()` patterns (not bare URL strings) when the HTTP client passes
query parameters, because aiohttp builds the full URL with the query string and
a bare URL match will fail.

### Capturing request URLs

Use `aioresponses` callbacks to inspect the actual request URL:

```python
from typing import Any

def callback(url: Any, **kwargs: Any) -> CallbackResult:
    captured_urls.append(str(url))
    return CallbackResult(payload=response_data)

m.get(URL_RE, callback=callback)
```

### Test organization

Tests are organized by module and by functional area within each module:

- `test_config.py` — happy path, env var overrides, validation errors, edge cases
- `test_poller.py` — `_parse_pr`, client lifecycle, fetch methods, deduplication,
  repo filtering, rate limiting, error handling, pagination, static methods,
  config updates

Each test class groups related tests. Async test methods are auto-detected
by pytest-asyncio (no decorator needed).

## Continuous integration

The project uses GitHub Actions for CI (`.github/workflows/ci.yml`). On every
push and pull request to `main` or `develop`, two jobs run **in parallel**:

### Lint & type check

1. **Lockfile verification** -- `uv lock --check` (ensures `uv.lock` matches `pyproject.toml`)
2. **Lint** -- `ruff check .`
3. **Format** -- `ruff format --check .`
4. **Type check** -- `mypy forgewatch`
5. **ShellCheck** -- lints shell scripts

### Test & audit

1. **Tests** -- `pytest` (parallel via `pytest-xdist`, with coverage)
2. **Coverage gate** -- fails if total coverage drops below 90% (enforced by both `--cov-fail-under` and the PR coverage comment action)
3. **Dependency audit** -- `pip-audit` (scans installed packages for known CVEs)

Both jobs must pass before merging.

### Publish pipeline

A separate workflow (`.github/workflows/publish.yml`) handles package
publishing to PyPI and TestPyPI:

**Triggers:**

- **Push to `develop`** (path-filtered: `forgewatch/**`, `pyproject.toml`,
  `uv.lock`) -- publishes a dev build to TestPyPI
- **GitHub Release published** -- publishes the release to PyPI

**Jobs (sequential):**

1. **CI gate** -- reuses `ci.yml` via `workflow_call` (all lint + tests must pass)
2. **Build** -- produces sdist + wheel with `uv build`. On develop pushes,
   auto-stamps a dev version (`x.y.z.devN` using `GITHUB_RUN_NUMBER`) for
   unique TestPyPI uploads
3. **Publish to TestPyPI** -- uploads via `pypa/gh-action-pypi-publish` with
   OIDC Trusted Publishing (no API tokens needed)
4. **Publish to PyPI** -- only on `release` events, uploads to the real index
   via OIDC Trusted Publishing

Authentication uses **OIDC Trusted Publisher** (`id-token: write` permission)
with separate GitHub environments (`testpypi` and `pypi`). No API tokens or
secrets need to be configured -- PyPI trusts the GitHub Actions workflow
directly.

## Pre-commit hooks

The project includes a `.pre-commit-config.yaml` with:

- **ruff** -- lint and format checks (via `ruff-pre-commit`)
- **mypy** -- type checking

To set up pre-commit hooks locally:

```bash
uv run pre-commit install       # install hooks
uv run pre-commit run --all     # run on all files
```

Once installed, hooks run automatically on every `git commit`.

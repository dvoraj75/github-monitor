# Development guide

This document covers the development setup, tooling configuration, coding
conventions, and testing approach for github-monitor.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended package manager)

## Setup

```bash
git clone https://github.com/<you>/github-monitor.git
cd github-monitor
uv sync          # installs runtime deps + dev dependency group
```

This installs the project in editable mode along with all dev tools (pytest,
ruff, mypy, etc.).

## Project structure

```
github_monitor/          # Main package
├── __init__.py          # __version__ = "0.1.0"
├── __main__.py          # python -m entry point
├── config.py            # Config loading + validation
├── poller.py            # GitHub API client
├── store.py             # State store (Phase 4)
├── dbus_service.py      # D-Bus interface (Phase 5)
├── notifier.py          # Desktop notifications (Phase 6)
└── daemon.py            # Main daemon loop (Phase 7)

tests/
├── test_config.py       # 17 tests
├── test_poller.py       # 21 tests
├── test_store.py        # 24 tests
├── test_dbus_service.py # 28 tests
└── test_notifier.py     # 24 tests
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
uv run pytest            # 114 tests, ~8 seconds
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
target-version = "py313"
line-length = 88

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
    "PLR2004", # magic values are fine in tests
    "SLF001",  # private member access is fine in tests
    "INP001",  # tests don't need __init__.py
    "ARG001",  # unused callback args (aioresponses callbacks)
]
```

### mypy

```toml
[tool.mypy]
python_version = "3.13"
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
```

`asyncio_mode = "auto"` means async test functions are automatically detected
and run in an event loop — no need for `@pytest.mark.asyncio` decorators.

## Build system

The project uses [hatchling](https://hatch.pypa.io/) as its build backend:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Hatchling is required so that `uv` treats the project as an installable package,
which is needed for `from github_monitor import ...` to work in tests.

## Dependencies

Dependencies are managed in `pyproject.toml`:

```toml
[project]
dependencies = [
    "aiohttp>=3.9,<4",
    "dbus-next>=0.2.3,<1",
]

[dependency-groups]      # PEP 735 — used by uv
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "aioresponses>=0.7",
    "ruff>=0.8",
    "mypy>=1.13",
]
```

Dev dependencies use `[dependency-groups]` (PEP 735) rather than
`[project.optional-dependencies]` because the project uses `uv` as its package
manager.

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
- Use `asyncio.sleep()` for waits (rate limit, poll interval)

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

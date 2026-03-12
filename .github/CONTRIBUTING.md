# Contributing to ForgeWatch

Thanks for your interest in contributing! This guide will help you get started.

## Getting started

### Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** -- used for dependency management and running tools
- **Linux** -- ForgeWatch relies on D-Bus and systemd (see [Architecture](#project-architecture) below)

For system tray indicator work, you'll also need GTK3 and AppIndicator3 system
packages -- see [docs/development.md](../docs/development.md) for details.

### Development setup

```bash
git clone https://github.com/dvoraj75/forgewatch.git
cd forgewatch
uv sync                    # install all dependencies (runtime + dev)
uv run pre-commit install  # set up pre-commit hooks
```

### Verify everything works

```bash
uv run pytest              # run all tests (~170 tests, parallel)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy forgewatch     # type check (strict mode)
```

## Making changes

### Branching

1. Fork the repository
2. Create a feature branch from `develop` (not `main`)
3. Use descriptive branch names: `fix/notification-crash`, `feat/label-filter`, etc.

### Code style

ForgeWatch enforces strict coding conventions:

- **Type hints everywhere** -- `str | None`, not `Optional[str]`
- **`from __future__ import annotations`** in every file
- **Frozen dataclasses** for all value objects (`PullRequest`, `Config`, etc.)
- **Async I/O only** -- no blocking calls in the event loop
- **120-character line length**
- **Ruff** for linting (all rules enabled) and formatting (black-compatible)
- **mypy strict mode** for type checking

See [docs/development.md](../docs/development.md) for the full conventions guide.

### Testing

Every change should include tests. The project maintains 90%+ code coverage.

```bash
uv run pytest                              # run all tests
uv run pytest tests/test_notifier.py       # run a specific test file
uv run pytest tests/test_notifier.py -k "test_single_pr"  # run a specific test
```

Key testing patterns:
- `aioresponses` for mocking HTTP requests
- `unittest.mock` for subprocesses and D-Bus
- Each test file has a `_make_pr()` helper for building test data
- Async tests are auto-detected (no decorator needed)

If you modify CLI subcommands (`forgewatch/cli/`), also run:

```bash
uv run pytest tests/test_cli_setup.py tests/test_cli_service.py tests/test_cli_uninstall.py -v
```

The CLI package uses **stdlib only** (no extra dependencies).

## Running all checks

Before submitting a PR, run the full check suite:

```bash
uv lock --check                # verify lockfile matches pyproject.toml
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run mypy forgewatch         # type check
uv run pytest                  # tests (all passing, 90%+ coverage)
uv run pip-audit               # dependency vulnerability scan
```

All of these run automatically in CI. Pre-commit hooks catch lint and type
errors on every commit.

## Project architecture

ForgeWatch is structured as an async daemon with optional components:

```
forgewatch/
  __main__.py       CLI entry point (argparse dispatch)
  daemon.py         Orchestrator (poll loop, signal handling)
  poller.py         GitHub API client (aiohttp, pagination, rate limits)
  store.py          In-memory PR state + diff computation
  notifier.py       Desktop notifications (notify-send)
  dbus_service.py   D-Bus interface (dbus-next)
  config.py         TOML config loading + validation
  url_opener.py     Shared URL opener (XDG portal + xdg-open)
  cli/              Management subcommands (setup, service, uninstall)
  indicator/        System tray icon + popup window (GTK3, separate process)
```

For the full architecture guide, see [docs/architecture.md](../docs/architecture.md).

## Pull requests

1. Ensure all checks pass (see above)
2. Write a clear PR description explaining **what** changed and **why**
3. Reference any related issues (`Fixes #123`, `Closes #456`)
4. Keep PRs focused -- one feature or fix per PR
5. Update documentation if your change affects user-facing behaviour
6. Add a CHANGELOG entry under the `[Unreleased]` section if applicable

## Reporting issues

Use the [issue templates](https://github.com/dvoraj75/forgewatch/issues/new/choose)
for bug reports and feature requests. Include reproduction steps, Python version,
and OS for bug reports.

## Questions?

Open a [discussion](https://github.com/dvoraj75/forgewatch/issues) or comment
on an existing issue. We're happy to help you get oriented in the codebase.

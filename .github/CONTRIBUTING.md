# Contributing to github-monitor

Thanks for your interest in contributing!

## Development setup

```bash
git clone https://github.com/dvoraj75/github-monitor.git
cd github-monitor
uv sync
```

## Running checks

```bash
uv run pytest                  # tests (ALL passing)
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run mypy github_monitor     # type check
```

All four must pass before a PR will be merged.

## Code style

- Full type hints everywhere (`str | None`, not `Optional[str]`)
- `from __future__ import annotations` in every file
- Frozen dataclasses for data models
- All I/O is async
- See [docs/development.md](../docs/development.md) for full conventions

## Pull requests

1. Fork the repo and create a feature branch
2. Make your changes
3. Ensure all checks pass (`pytest`, `ruff check`, `ruff format --check`, `mypy`)
4. Open a PR with a clear description of the change

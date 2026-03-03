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
uv lock --check                # verify lockfile matches pyproject.toml
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run mypy github_monitor     # type check
uv run pytest                  # tests (ALL passing)
uv run pip-audit               # dependency vulnerability scan
```

If you modify shell scripts (`install.sh`, `update.sh`, `uninstall.sh`), also
run [ShellCheck](https://www.shellcheck.net/): `shellcheck *.sh`

All checks must pass before a PR will be merged (CI runs them automatically).

## Code style

- Full type hints everywhere (`str | None`, not `Optional[str]`)
- `from __future__ import annotations` in every file
- Frozen dataclasses for data models
- All I/O is async
- See [docs/development.md](../docs/development.md) for full conventions

## Pull requests

1. Fork the repo and create a feature branch
2. Make your changes
3. Ensure all checks pass (see "Running checks" above)
4. Open a PR with a clear description of the change

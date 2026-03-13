# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - Unreleased

### Added

- Pagination cap warning -- the poller now logs a warning when the page limit is reached and more results are available, suggesting the user narrow their repo filter
- Configurable indicator settings via a new `[indicator]` TOML section -- `reconnect_interval`, `window_width`, and `max_window_height` can now be tuned without code changes
- Unknown config key warnings -- `load_config()` now logs a warning for any unrecognised top-level key, helping catch typos early
- Repo-based notification grouping via a new `[notifications]` config section -- set `grouping = "repo"` to receive per-repository summary notifications instead of a single flat list
- Per-repo notification overrides via `[notifications.repos."owner/repo"]` -- disable notifications for noisy repos (`enabled = false`), override urgency (`urgency = "critical"`), or set a custom individual-vs-summary threshold per repository

### Changed

- Improved first-run experience -- `ConfigError` is now caught and displayed as a user-friendly log message instead of a raw traceback. Missing config suggests running `forgewatch setup`, invalid config suggests checking the config file. The daemon exits cleanly with code 1
- Logging is now initialised before config loading so that config errors are properly formatted
- Config validation now collects all errors and reports them in a single `ConfigError`, so users can fix every problem in one pass instead of playing whack-a-mole
- Validation error messages now include actionable hints (e.g. `ghp_` token prefix example, `GitHub recommends 300s` for poll interval, `octocat/Hello-World` for repo format)

## [1.4.1] - 2026-03-12

### Fixed

- Network errors (e.g. connectivity loss) no longer wipe the PR store -- the poller now re-raises exceptions instead of silently returning an empty list, so the daemon preserves last-known-good state and avoids spurious "new PR" notifications on recovery

### Changed

- Lowered minimum Python version from 3.13 to 3.11 -- no code changes required; the codebase only uses `tomllib`, `enum.StrEnum`, and `datetime.UTC` from 3.11+
- Ruff `target-version` set to `py311` and mypy `python_version` set to `3.11` to match the new floor
- CI test job now runs a Python version matrix (3.11, 3.12, 3.13, 3.14) -- all versions must pass
- Coverage comment and `pip-audit` scoped to Python 3.13 to avoid duplicate PR comments and redundant audit runs
- Added PyPI classifiers for Python 3.11, 3.12, and 3.14

## [1.4.0] - 2026-03-10

### Added

- GitHub Actions publish workflow (`publish.yml`) for automated PyPI and TestPyPI publishing using OIDC Trusted Publishing — no API tokens required
- Made CI workflow (`ci.yml`) reusable via `workflow_call` trigger so the publish pipeline can gate on lint + tests without duplicating steps
- Automatic dev version stamping (`x.y.z.devN`) on develop branch pushes, using the CI run number for unique TestPyPI uploads
- Path-filtered publish trigger — only `forgewatch/**`, `pyproject.toml`, and `uv.lock` changes on `develop` trigger the publish pipeline

### Changed

- Moved `gbulb` from optional `[indicator]` extra into core dependencies — `pip install forgewatch` now includes everything needed, no extras syntax required
- **Rebrand**: renamed project from `github-monitor` to `forgewatch` — Python package (`github_monitor` -> `forgewatch`), CLI entry points, D-Bus bus name (`org.forgewatch.Daemon`), systemd service files, config directory (`~/.config/forgewatch/`), icon resources, and all metadata
- Removed deprecated shell scripts (`install.sh`, `update.sh`, `uninstall.sh`) — replaced by CLI subcommands in v1.3.0
- Coverage comment step in CI now conditional on `pull_request` events to avoid failures when called from the publish pipeline

### Fixed

- Stale pre-rebrand references in `docs/systemd.md`, `docs/modules/daemon.md`, and `tests/test_cli_systemd.py` still showing old "GitHub PR Monitor" description

## [1.3.1] - 2026-03-08

### Added

- Dynamic tooltip on the tray icon showing connection state, open PR count, and review-requested status (via `get_tooltip()` in `_tray_state.py`)

### Changed

- Version is now read from package metadata (`importlib.metadata.version()`) instead of being hardcoded in `__init__.py`

### Fixed

- Indicator tests (`test_indicator_tray.py`, `test_indicator_window.py`) failing on systems with GTK installed — `gi` module stubs now always override `sys.modules` instead of being skipped when the real `gi` is present

## [1.3.0] - 2026-03-05

### Added

- CLI management subcommands replacing the shell scripts with a Python-native solution:
  - `forgewatch setup` -- interactive config wizard + systemd service installation (supports `--config-only` and `--service-only` flags)
  - `forgewatch service` -- systemd service management (install, start, stop, restart, status, enable, disable)
  - `forgewatch uninstall` -- stop services, remove unit files, optionally remove config
- Bundled systemd service files as package data (accessed via `importlib.resources`)

### Deprecated

- `install.sh` -- use `forgewatch setup` instead
- `update.sh` -- use `pip install --upgrade forgewatch` instead
- `uninstall.sh` -- use `forgewatch uninstall` instead

### Fixed

- Config reload (SIGHUP) did not take effect until the current poll interval expired -- the new `poll_interval` (and an immediate re-poll) now applies instantly after reload

### Changed

- Split CI pipeline into two parallel jobs: **Lint & type check** and **Test & audit** for faster feedback
- Added `uv lock --check` step to verify lockfile stays in sync with `pyproject.toml`
- Added ShellCheck to lint shell scripts (`install.sh`, `update.sh`, `uninstall.sh`)
- Added `pip-audit` dependency vulnerability scanning to CI
- Pinned CI dependencies with `uv sync --locked` to ensure reproducible builds
- Enforced minimum 90% test coverage gate via `--cov-fail-under=90` (locally and in CI)
- Added PR coverage comment via `orgoro/coverage` action with 90% threshold

## [1.2.1] - 2026-03-03

### Fixed

- Indicator app tests failing in CI due to missing GTK system packages — deferred GTK-dependent imports in `app.py` and added `gi` module stubs in tests

## [1.2.0] - 2026-03-03

### Added

- System tray indicator with live PR count and clickable popup window (GTK3/AppIndicator3)
  - D-Bus client with auto-reconnect to daemon
  - Popup window with scrollable PR list, status footer, and click-to-open
  - Tray icon with colour-coded states (idle, active, alert, disconnected)
  - Show/Hide toggle, Refresh, and Quit menu items
- Light and dark icon theme support via `icon_theme` config option
- Shared URL opener module (XDG Desktop Portal with xdg-open fallback), used by both notifier and indicator
- Systemd user service for the indicator (`forgewatch-indicator.service`)
- Comprehensive test suite for all indicator modules

### Fixed

- Indicator not reconnecting after daemon restart (stale reconnect handle prevented retry scheduling)
- `install.sh` not restarting already-running services during reinstall

## [1.1.0] - 2026-03-01

### Added

- Runtime-configurable options in `config.toml`: log level, notifications toggle, D-Bus toggle, notification urgency/threshold, max retries, `notify_on_first_poll`, and GitHub Enterprise base URL
- `update.sh` script for in-place upgrades with git-aware safety checks
- `systemctl --user reload forgewatch` support via `ExecReload` in systemd service
- Pre-commit hooks for ruff and mypy (`.pre-commit-config.yaml`)

### Changed

- Config dataclass is now frozen (immutable) to prevent accidental mutation
- Notification threshold and urgency are configurable (previously hardcoded)
- GitHub API base URL and max retries are configurable, enabling GitHub Enterprise support
- D-Bus interface can be disabled via config for headless/container environments

### Fixed

- Notification click-to-open broken under systemd sandbox — now uses XDG Desktop Portal over D-Bus with fallback to `xdg-open`
- Config reload (SIGHUP) ignored the `-c` config path, always reloading from default location

### Improved

- Reuse single aiohttp session for avatar downloads within a notification batch, reducing connection overhead

## [1.0.0] - 2026-03-01

### Added

- GitHub PR polling via Search Issues API with pagination and rate limiting
- In-memory state store with diff computation (new/closed/updated PRs)
- Desktop notifications via `notify-send` with author avatars and clickable links
- D-Bus session bus interface (`org.forgewatch.Daemon`) with methods: `GetPullRequests`, `GetStatus`, `Refresh` and signal: `PullRequestsChanged`
- TOML configuration with environment variable override support (`GITHUB_TOKEN`)
- Exponential backoff retries for API failures
- Graceful shutdown (SIGTERM/SIGINT) and config reload (SIGHUP)
- Systemd user service with security hardening
- 151 tests with full coverage

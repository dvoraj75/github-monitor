# `config.py` -- API reference

Module: `github_monitor.config`

Handles loading, validating, and representing the daemon's configuration.

## Constants

| Name | Type | Value | Description |
|---|---|---|---|
| `CONFIG_DIR` | `Path` | `~/.config/github-monitor` | Default config directory |
| `CONFIG_PATH` | `Path` | `~/.config/github-monitor/config.toml` | Default config file path |

Internal constants (prefixed with `_`):

| Name | Type | Value | Description |
|---|---|---|---|
| `_REPO_PATTERN` | `re.Pattern` | `^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$` | Regex for validating `owner/name` repo format |
| `_MIN_POLL_INTERVAL` | `int` | `30` | Minimum allowed poll interval in seconds |
| `_VALID_LOG_LEVELS` | `frozenset[str]` | `{"debug", "info", "warning", "error"}` | Allowed values for `log_level` |
| `_VALID_URGENCIES` | `frozenset[str]` | `{"low", "normal", "critical"}` | Allowed values for `notification_urgency` |
| `_VALID_ICON_THEMES` | `frozenset[str]` | `{"light", "dark"}` | Allowed values for `icon_theme` |

## `ConfigError`

```python
class ConfigError(Exception): ...
```

Raised when configuration is invalid or missing. All validation failures produce
a `ConfigError` with a human-readable message describing what went wrong.

**Examples of error messages:**

- `"Config file not found: /path/to/config.toml"`
- `"Invalid TOML in /path/to/config.toml: ..."`
- `"github_token is required (set in config or GITHUB_TOKEN env var)"`
- `"github_username is required"`
- `"poll_interval must be an integer, got str"`
- `"poll_interval must be >= 30, got 10"`
- `"repos must be a list"`
- `"Invalid repo format: 'not-valid' (expected 'owner/name')"`
- `"log_level must be one of ['debug', 'error', 'info', 'warning'], got 'verbose'"`
- `"notifications_enabled must be a boolean, got str"`
- `"github_base_url must start with http:// or https://, got 'ftp://...'"`
- `"max_retries must be >= 0, got -1"`
- `"notification_threshold must be >= 1, got 0"`
- `"notification_urgency must be one of ['critical', 'low', 'normal'], got 'extreme'"`
- `"icon_theme must be one of ['dark', 'light'], got 'blue'"`

## `Config`

```python
@dataclass(frozen=True)
class Config:
    github_token: str
    github_username: str
    poll_interval: int = 300
    repos: list[str] = field(default_factory=list)
    log_level: str = "info"
    notify_on_first_poll: bool = False
    notifications_enabled: bool = True
    dbus_enabled: bool = True
    github_base_url: str = "https://api.github.com"
    max_retries: int = 3
    notification_threshold: int = 3
    notification_urgency: str = "normal"
    icon_theme: str = "light"
```

An immutable (frozen) dataclass holding validated configuration values.

| Field | Type | Default | Description |
|---|---|---|---|
| `github_token` | `str` | (required) | GitHub PAT with `repo` scope |
| `github_username` | `str` | (required) | GitHub username for search queries |
| `poll_interval` | `int` | `300` | Poll interval in seconds (>= 30) |
| `repos` | `list[str]` | `[]` | Repo filter (`owner/name` format); empty = all |
| `log_level` | `str` | `"info"` | Log level: `debug`, `info`, `warning`, `error` |
| `notify_on_first_poll` | `bool` | `False` | Notify for PRs found on first poll |
| `notifications_enabled` | `bool` | `True` | Enable/disable desktop notifications |
| `dbus_enabled` | `bool` | `True` | Enable/disable D-Bus interface |
| `github_base_url` | `str` | `"https://api.github.com"` | GitHub API base URL (for GHE) |
| `max_retries` | `int` | `3` | Max HTTP retries for 5xx errors (>= 0) |
| `notification_threshold` | `int` | `3` | Individual vs. summary notification cutoff (>= 1) |
| `notification_urgency` | `str` | `"normal"` | Notification urgency: `low`, `normal`, `critical` |
| `icon_theme` | `str` | `"light"` | Icon theme for tray indicator: `light`, `dark` |

The dataclass is frozen, so fields cannot be modified after creation:

```python
cfg = load_config()
cfg.poll_interval = 60  # raises AttributeError
```

## `load_config()`

```python
def load_config(path: Path | str | None = None) -> Config:
```

Load configuration from a TOML file and return a validated `Config` instance.

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `path` | `Path \| str \| None` | `None` | Explicit config file path. If `None`, resolved via env var or default. |

### Returns

A `Config` instance with all fields validated.

### Raises

- `ConfigError` -- if the config file is not found, contains invalid TOML, or
  fails validation

### Behavior

1. Resolves the file path via `_resolve_path(path)`
2. Reads and parses the TOML file
3. Applies `GITHUB_TOKEN` env var override (if set and non-empty)
4. Validates all fields via `_validate()`
5. Returns a `Config` instance

### Example

```python
from github_monitor.config import load_config

# Default path (~/.config/github-monitor/config.toml)
cfg = load_config()

# Explicit path
cfg = load_config("/etc/github-monitor/config.toml")

# String path also works
cfg = load_config("./my-config.toml")
```

## `_resolve_path()` (internal)

```python
def _resolve_path(path: Path | str | None) -> Path:
```

Resolves the config file path using three-tier precedence:

1. If `path` is provided, use it (converting `str` to `Path` if needed)
2. If `GITHUB_MONITOR_CONFIG` env var is set, use its value
3. Fall back to `CONFIG_PATH` (`~/.config/github-monitor/config.toml`)

### Raises

- `ConfigError` -- if the resolved path does not exist

## Validation helpers (internal)

Validation is split into reusable helper functions:

### `_require_str(raw, key, error_msg) -> str`

Extracts a required non-empty string field. Raises `ConfigError` with the
provided message if the value is missing, empty, or not a string.

### `_validate_bool(raw, key, *, default) -> bool`

Extracts an optional boolean field with a default value. Raises `ConfigError`
if the value is present but not a boolean.

### `_validate_int_min(raw, key, *, default, minimum) -> int`

Extracts an optional integer field with a minimum bound. Raises `ConfigError`
if the value is not an integer or is below the minimum.

### `_validate_choice(raw, key, *, default, choices) -> str`

Extracts an optional string field validated against a set of allowed values.
The value is normalised to lowercase before comparison. Raises `ConfigError`
if the value is not a string or not in the allowed set.

### `_validate_base_url(raw) -> str`

Extracts and validates the `github_base_url` field. Must start with `http://`
or `https://`. Trailing slashes are stripped. Raises `ConfigError` on invalid
values.

### `_validate_repos(raw) -> list[str]`

Extracts and validates the `repos` list. Each entry must be a string matching
the `_REPO_PATTERN` regex (`owner/name` format). Raises `ConfigError` on
invalid values.

## `_validate()` (internal)

```python
def _validate(raw: dict[str, object]) -> Config:
```

Validates the raw TOML dict and returns a `Config` instance. Delegates to the
individual validation helpers above.

### Validation rules

1. `github_token` -- must be a `str` and non-empty (via `_require_str`)
2. `github_username` -- must be a `str` and non-empty (via `_require_str`)
3. `poll_interval` -- must be an `int` >= 30 (via `_validate_int_min`)
4. `repos` -- must be a `list` of strings matching `_REPO_PATTERN` (via `_validate_repos`)
5. `log_level` -- must be one of `_VALID_LOG_LEVELS` (via `_validate_choice`)
6. `notify_on_first_poll` -- must be a `bool` (via `_validate_bool`)
7. `notifications_enabled` -- must be a `bool` (via `_validate_bool`)
8. `dbus_enabled` -- must be a `bool` (via `_validate_bool`)
9. `github_base_url` -- must start with `http://` or `https://` (via `_validate_base_url`)
10. `max_retries` -- must be an `int` >= 0 (via `_validate_int_min`)
11. `notification_threshold` -- must be an `int` >= 1 (via `_validate_int_min`)
12. `notification_urgency` -- must be one of `_VALID_URGENCIES` (via `_validate_choice`)
13. `icon_theme` -- must be one of `_VALID_ICON_THEMES` (via `_validate_choice`)

## Tests

Tests in `tests/test_config.py` covering:

- Happy path (valid config, minimal config, string path)
- Environment variable overrides (`GITHUB_TOKEN`, `GITHUB_MONITOR_CONFIG`, token
  from env when missing in file)
- Validation errors (missing file, invalid TOML, missing token/username, invalid
  poll_interval type/value, invalid repo format, repos not a list)
- New config fields (log_level, notify_on_first_poll, notifications_enabled,
  dbus_enabled, github_base_url, max_retries, notification_threshold,
  notification_urgency, icon_theme) -- defaults, valid values, invalid types, edge cases
  (case-insensitivity, trailing slash stripping, zero retries)
- Edge cases (empty token/username strings, boundary poll_interval = 30)

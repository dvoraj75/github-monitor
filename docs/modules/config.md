# `config.py` -- API reference

Module: `forgewatch.config`

Handles loading, validating, and representing the daemon's configuration.

## Constants

| Name | Type | Value | Description |
|---|---|---|---|
| `CONFIG_DIR` | `Path` | `~/.config/forgewatch` | Default config directory |
| `CONFIG_PATH` | `Path` | `~/.config/forgewatch/config.toml` | Default config file path |

Internal constants (prefixed with `_`):

| Name | Type | Value | Description |
|---|---|---|---|
| `_REPO_PATTERN` | `re.Pattern` | `^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$` | Regex for validating `owner/name` repo format |
| `_MIN_POLL_INTERVAL` | `int` | `30` | Minimum allowed poll interval in seconds |
| `_VALID_LOG_LEVELS` | `frozenset[str]` | `{"debug", "info", "warning", "error"}` | Allowed values for `log_level` |
| `_VALID_URGENCIES` | `frozenset[str]` | `{"low", "normal", "critical"}` | Allowed values for `notification_urgency` |
| `_VALID_ICON_THEMES` | `frozenset[str]` | `{"light", "dark"}` | Allowed values for `icon_theme` |
| `_VALID_GROUPING_MODES` | `frozenset[str]` | `{"flat", "repo"}` | Allowed values for `notifications.grouping` |
| `_KNOWN_KEYS` | `frozenset[str]` | *(all recognised top-level keys)* | Used by `_warn_unknown_keys()` to detect typos |

## `ConfigError`

```python
class ConfigError(Exception): ...
```

Raised when configuration is invalid or missing. All validation failures produce
a `ConfigError` with a human-readable message describing what went wrong.

Validation now collects **all** errors and raises a single `ConfigError` with
every problem listed (one per line), so the user can fix everything in one pass.

**Examples of error messages:**

- `"Config file not found: /path/to/config.toml"`
- `"Invalid TOML in /path/to/config.toml: ..."`
- `"github_token is required (set in config.toml or export GITHUB_TOKEN=ghp_...)"`
- `"github_username is required"`
- `"poll_interval must be an integer, got str"`
- `"poll_interval must be >= 30, got 10 (GitHub recommends 300s for personal tokens)"`
- `"repos must be a list"`
- `"Invalid repo format: 'not-valid' (expected 'owner/name') — example: 'octocat/Hello-World'"`
- `"log_level must be one of ['debug', 'error', 'info', 'warning'], got 'verbose'"`
- `"notifications_enabled must be a boolean, got str"`
- `"github_base_url must start with http:// or https://, got 'ftp://...'"`
- `"max_retries must be >= 0, got -1"`
- `"notification_threshold must be >= 1, got 0"`
- `"notification_urgency must be one of ['critical', 'low', 'normal'], got 'extreme'"`
- `"icon_theme must be one of ['dark', 'light'], got 'blue'"`

## `RepoNotificationConfig`

```python
@dataclass(frozen=True)
class RepoNotificationConfig:
    enabled: bool = True
    urgency: str = "normal"
    threshold: int = 3
```

Per-repo notification overrides. Each instance corresponds to a
`[notifications.repos."owner/repo"]` entry in the config file.

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `bool` | `True` | Set to `False` to suppress notifications for this repo |
| `urgency` | `str` | `"normal"` | Notification urgency: `low`, `normal`, `critical` |
| `threshold` | `int` | `3` | Individual vs. summary notification cutoff (>= 1) |

## `NotificationConfig`

```python
@dataclass(frozen=True)
class NotificationConfig:
    grouping: str = "flat"
    repos: dict[str, RepoNotificationConfig] = field(default_factory=dict)
```

Notification grouping and per-repo settings from the `[notifications]` section.

| Field | Type | Default | Description |
|---|---|---|---|
| `grouping` | `str` | `"flat"` | Grouping mode: `flat` (single list) or `repo` (grouped by repository) |
| `repos` | `dict[str, RepoNotificationConfig]` | `{}` | Per-repo overrides keyed by `owner/name` |

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
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
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
| `notifications` | `NotificationConfig` | `NotificationConfig()` | Notification grouping and per-repo overrides |

The dataclass is frozen, so fields cannot be modified after creation:

```python
cfg = load_config()
cfg.poll_interval = 60  # raises AttributeError
```

## `IndicatorConfig`

```python
@dataclass(frozen=True)
class IndicatorConfig:
    reconnect_interval: int = 10
    window_width: int = 400
    max_window_height: int = 500
```

An immutable (frozen) dataclass holding validated indicator-specific settings
from the `[indicator]` TOML section.

| Field | Type | Default | Description |
|---|---|---|---|
| `reconnect_interval` | `int` | `10` | Seconds between D-Bus reconnect attempts (>= 1) |
| `window_width` | `int` | `400` | Popup window width in pixels (>= 200) |
| `max_window_height` | `int` | `500` | Maximum popup window height in pixels (>= 200) |

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
3. Warns about unrecognised top-level keys via `_warn_unknown_keys()`
4. Applies `GITHUB_TOKEN` env var override (if set and non-empty)
5. Validates all fields via `_validate()` (collects all errors before raising)
6. Returns a `Config` instance

### Example

```python
from forgewatch.config import load_config

# Default path (~/.config/forgewatch/config.toml)
cfg = load_config()

# Explicit path
cfg = load_config("/etc/forgewatch/config.toml")

# String path also works
cfg = load_config("./my-config.toml")
```

## `load_indicator_config()`

```python
def load_indicator_config(path: Path | str | None = None) -> IndicatorConfig:
```

Load indicator-specific configuration from the `[indicator]` TOML section and
return a validated `IndicatorConfig` instance.

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `path` | `Path \| str \| None` | `None` | Explicit config file path. If `None`, resolved via env var or default. |

### Returns

An `IndicatorConfig` instance with all fields validated.

### Raises

- `ConfigError` -- if the `[indicator]` section contains invalid values

### Behavior

1. Resolves the file path via `_resolve_path(path)`
2. If the file does not exist or contains invalid TOML, returns defaults
3. If the `[indicator]` section is missing, returns defaults
4. Validates all fields (collects all errors before raising)
5. Returns an `IndicatorConfig` instance

### Example

```python
from forgewatch.config import load_indicator_config

# Defaults when [indicator] section is absent
cfg = load_indicator_config()
assert cfg.reconnect_interval == 10
assert cfg.window_width == 400
assert cfg.max_window_height == 500

# Custom path
cfg = load_indicator_config("/etc/forgewatch/config.toml")
```

## `_resolve_path()` (internal)

```python
def _resolve_path(path: Path | str | None) -> Path:
```

Resolves the config file path using three-tier precedence:

1. If `path` is provided, use it (converting `str` to `Path` if needed)
2. If `FORGEWATCH_CONFIG` env var is set, use its value
3. Fall back to `CONFIG_PATH` (`~/.config/forgewatch/config.toml`)

### Raises

- `ConfigError` -- if the resolved path does not exist

## `_warn_unknown_keys()` (internal)

```python
def _warn_unknown_keys(raw: dict[str, object]) -> None:
```

Logs a warning for each top-level key not in `_KNOWN_KEYS`. Helps users
catch typos in their config file.

## Error-collecting validation helpers (internal)

These helpers append error messages to an `errors` list instead of raising
immediately, enabling multi-error reporting.

### `_collect_str(raw, key, error_msg, errors) -> str`

Extracts a required non-empty string field. Appends to `errors` if the value
is missing, empty, or not a string.

### `_collect_bool(raw, key, *, default, errors) -> bool`

Extracts an optional boolean field with a default value. Appends to `errors`
if the value is present but not a boolean.

### `_collect_int_min(raw, key, *, default, minimum, errors) -> int`

Extracts an optional integer field with a minimum bound. Appends to `errors`
if the value is not an integer or is below the minimum.

### `_collect_choice(raw, key, *, default, choices, errors) -> str`

Extracts an optional string field validated against a set of allowed values.
The value is normalised to lowercase before comparison. Appends to `errors`
if the value is not a string or not in the allowed set.

### `_collect_base_url(raw, errors) -> str`

Extracts and validates the `github_base_url` field. Must start with `http://`
or `https://`. Trailing slashes are stripped. Appends to `errors` on invalid
values.

### `_collect_repos(raw, errors) -> list[str]`

Extracts and validates the `repos` list. Each entry must be a string matching
the `_REPO_PATTERN` regex (`owner/name` format). Appends to `errors` on
invalid values.

## Legacy validation helpers (internal)

These raise-immediately helpers are kept for backward compatibility but are no
longer used by `_validate()`:

### `_require_str(raw, key, error_msg) -> str`

Extracts a required non-empty string field. Raises `ConfigError` immediately.

### `_validate_bool(raw, key, *, default) -> bool`

Extracts an optional boolean field. Raises `ConfigError` immediately.

### `_validate_int_min(raw, key, *, default, minimum) -> int`

Extracts an optional integer field with a minimum bound. Raises `ConfigError`
immediately.

### `_validate_choice(raw, key, *, default, choices) -> str`

Extracts an optional string field validated against allowed values. Raises
`ConfigError` immediately.

### `_validate_base_url(raw) -> str`

Extracts and validates `github_base_url`. Raises `ConfigError` immediately.

### `_validate_repos(raw) -> list[str]`

Extracts and validates the `repos` list. Raises `ConfigError` immediately.

## `_validate()` (internal)

```python
def _validate(raw: dict[str, object]) -> Config:
```

Validates the raw TOML dict and returns a `Config` instance. Collects **all**
validation errors via the `_collect_*` helpers and raises a single
`ConfigError` with every problem reported, so the user can fix everything in
one pass.

### Validation rules

1. `github_token` -- must be a `str` and non-empty (via `_collect_str`)
2. `github_username` -- must be a `str` and non-empty (via `_collect_str`)
3. `poll_interval` -- must be an `int` >= 30 (via `_collect_int_min`); error enhanced with GitHub recommendation
4. `repos` -- must be a `list` of strings matching `_REPO_PATTERN` (via `_collect_repos`); error includes example
5. `log_level` -- must be one of `_VALID_LOG_LEVELS` (via `_collect_choice`)
6. `notify_on_first_poll` -- must be a `bool` (via `_collect_bool`)
7. `notifications_enabled` -- must be a `bool` (via `_collect_bool`)
8. `dbus_enabled` -- must be a `bool` (via `_collect_bool`)
9. `github_base_url` -- must start with `http://` or `https://` (via `_collect_base_url`)
10. `max_retries` -- must be an `int` >= 0 (via `_collect_int_min`)
11. `notification_threshold` -- must be an `int` >= 1 (via `_collect_int_min`)
12. `notification_urgency` -- must be one of `_VALID_URGENCIES` (via `_collect_choice`)
13. `icon_theme` -- must be one of `_VALID_ICON_THEMES` (via `_collect_choice`)
14. `notifications` -- validated via `_validate_notifications()` (see below)

## `_validate_notifications()` (internal)

```python
def _validate_notifications(raw: dict[str, object]) -> NotificationConfig:
```

Validates the `[notifications]` TOML section. Returns `NotificationConfig()`
with defaults if the section is absent. Checks:

- `notifications` must be a table (if present)
- `grouping` must be a string in `_VALID_GROUPING_MODES` (case-insensitive)
- `repos` must be a table (if present); each entry validated by `_validate_repo_notification()`

## `_validate_repo_notification()` (internal)

```python
def _validate_repo_notification(repo_name: str, repo_raw: dict[str, object]) -> RepoNotificationConfig:
```

Validates a single `[notifications.repos."owner/repo"]` entry. Checks:

- `enabled` must be a boolean (default: `True`)
- `urgency` must be a string in `_VALID_URGENCIES` (case-insensitive, default: `"normal"`)
- `threshold` must be an integer >= 1 (default: `3`)

## Tests

Tests in `tests/test_config.py` covering:

- Happy path (valid config, minimal config, string path)
- Environment variable overrides (`GITHUB_TOKEN`, `FORGEWATCH_CONFIG`, token
  from env when missing in file)
- Validation errors (missing file, invalid TOML, missing token/username, invalid
  poll_interval type/value, invalid repo format, repos not a list)
- New config fields (log_level, notify_on_first_poll, notifications_enabled,
  dbus_enabled, github_base_url, max_retries, notification_threshold,
  notification_urgency, icon_theme) -- defaults, valid values, invalid types, edge cases
  (case-insensitivity, trailing slash stripping, zero retries)
- Edge cases (empty token/username strings, boundary poll_interval = 30)
- Unknown key warnings (typos logged, known keys silent, `[indicator]` section recognised)
- Multi-error collection (multiple validation failures in a single `ConfigError`,
  actionable hints in error messages)
- `IndicatorConfig` via `load_indicator_config()` -- defaults, custom values,
  partial values, missing file, invalid TOML, boundary validation for each field,
  wrong types, multiple errors collected, frozen dataclass
- `NotificationConfig` -- defaults when section missing, grouping modes (flat,
  repo), invalid grouping, case-insensitive grouping, per-repo full config,
  disabled repos, invalid urgency/threshold/enabled types, multiple repos,
  `notifications` not a table

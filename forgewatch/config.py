"""Configuration loading and validation for forgewatch."""

from __future__ import annotations

import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "forgewatch"
CONFIG_PATH = CONFIG_DIR / "config.toml"

_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$")

_MIN_POLL_INTERVAL = 30
_VALID_LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})
_VALID_URGENCIES = frozenset({"low", "normal", "critical"})
_VALID_ICON_THEMES = frozenset({"light", "dark"})
_VALID_GROUPING_MODES = frozenset({"flat", "repo"})

_KNOWN_KEYS = frozenset(
    {
        "github_token",
        "github_username",
        "poll_interval",
        "repos",
        "log_level",
        "notify_on_first_poll",
        "notifications_enabled",
        "dbus_enabled",
        "github_base_url",
        "max_retries",
        "notification_threshold",
        "notification_urgency",
        "icon_theme",
        "indicator",
        "notifications",
    }
)
_KNOWN_INDICATOR_KEYS = frozenset({"reconnect_interval", "window_width", "max_window_height"})
_KNOWN_NOTIFICATIONS_KEYS = frozenset({"grouping", "repos"})
_KNOWN_REPO_NOTIFICATION_KEYS = frozenset({"enabled", "urgency", "threshold"})

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""


@dataclass(frozen=True)
class RepoNotificationConfig:
    """Per-repo notification overrides.

    ``urgency`` and ``threshold`` use ``None`` to mean "inherit the
    global value".  Only an explicit TOML setting produces a non-None
    value, so the notifier can distinguish "user set urgency" from
    "user didn't set urgency (should inherit global)".
    """

    enabled: bool = True
    urgency: str | None = None
    threshold: int | None = None


@dataclass(frozen=True)
class NotificationConfig:
    """Notification grouping and per-repo settings."""

    grouping: str = "flat"
    repos: dict[str, RepoNotificationConfig] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    """Validated configuration for forgewatch."""

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


@dataclass(frozen=True)
class IndicatorConfig:
    """Configuration for the indicator process."""

    reconnect_interval: int = 10
    window_width: int = 400
    max_window_height: int = 500


def load_config(path: Path | str | None = None) -> Config:
    """Load and validate config from TOML file.

    Path resolution precedence:
        1. Explicit ``path`` argument
        2. ``FORGEWATCH_CONFIG`` env var
        3. Default: ``~/.config/forgewatch/config.toml``

    The ``github_token`` value can be overridden by the
    ``GITHUB_TOKEN`` env var (takes precedence over the file value).
    """
    config_path = _resolve_path(path)

    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise ConfigError(msg)

    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        msg = f"Invalid TOML in {config_path}: {exc}"
        raise ConfigError(msg) from exc

    # Warn about unknown top-level keys (possible typos).
    _warn_unknown_keys(raw)

    # Env var override for token
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        raw["github_token"] = env_token

    return _validate(raw)


def load_indicator_config(path: Path | str | None = None) -> IndicatorConfig:
    """Load indicator-specific config from the ``[indicator]`` TOML section.

    Returns ``IndicatorConfig`` with defaults if the section is missing
    or the file cannot be read.  Validation errors raise ``ConfigError``.
    """
    config_path = _resolve_path(path)

    if not config_path.exists():
        return IndicatorConfig()

    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError:
        return IndicatorConfig()

    section = raw.get("indicator")
    if not isinstance(section, dict):
        return IndicatorConfig()

    errors: list[str] = []

    reconnect_interval = _collect_int_min(
        section,
        "reconnect_interval",
        default=10,
        minimum=1,
        errors=errors,
    )
    window_width = _collect_int_min(
        section,
        "window_width",
        default=400,
        minimum=200,
        errors=errors,
    )
    max_window_height = _collect_int_min(
        section,
        "max_window_height",
        default=500,
        minimum=200,
        errors=errors,
    )

    if errors:
        msg = "\n".join(errors)
        raise ConfigError(msg)

    return IndicatorConfig(
        reconnect_interval=reconnect_interval,
        window_width=window_width,
        max_window_height=max_window_height,
    )


def _resolve_path(path: Path | str | None) -> Path:
    """Determine which config file path to use."""
    if path is not None:
        return Path(path)

    env_path = os.environ.get("FORGEWATCH_CONFIG")
    if env_path:
        return Path(env_path)

    return CONFIG_PATH


def _warn_unknown_keys(raw: dict[str, object]) -> None:
    """Log warnings for any unrecognised config keys.

    Checks top-level keys as well as keys inside the ``[indicator]``
    and ``[notifications]`` subsections so that typos like
    ``reconnect_intervel`` are surfaced instead of silently ignored.
    """
    unknown = set(raw.keys()) - _KNOWN_KEYS
    for key in sorted(unknown):
        logger.warning("Unknown config key: %r (possible typo?)", key)

    indicator = raw.get("indicator")
    if isinstance(indicator, dict):
        unknown_ind = set(indicator.keys()) - _KNOWN_INDICATOR_KEYS
        for key in sorted(unknown_ind):
            logger.warning("Unknown key in [indicator]: %r (possible typo?)", key)

    notifications = raw.get("notifications")
    if isinstance(notifications, dict):
        unknown_notif = set(notifications.keys()) - _KNOWN_NOTIFICATIONS_KEYS
        for key in sorted(unknown_notif):
            logger.warning("Unknown key in [notifications]: %r (possible typo?)", key)

        repos_section = notifications.get("repos")
        if isinstance(repos_section, dict):
            for repo_name, repo_raw in repos_section.items():
                if isinstance(repo_raw, dict):
                    unknown_repo = set(repo_raw.keys()) - _KNOWN_REPO_NOTIFICATION_KEYS
                    for key in sorted(unknown_repo):
                        logger.warning(
                            "Unknown key in [notifications.repos.%r]: %r (possible typo?)",
                            repo_name,
                            key,
                        )


# ---------------------------------------------------------------------------
# Error-collecting validation helpers
# ---------------------------------------------------------------------------


def _collect_str(
    raw: dict[str, object],
    key: str,
    error_msg: str,
    errors: list[str],
) -> str:
    """Extract a required non-empty string, appending to *errors* on failure."""
    value = raw.get(key, "")
    if not value or not isinstance(value, str):
        errors.append(error_msg)
        return ""
    return value


def _collect_bool(
    raw: dict[str, object],
    key: str,
    *,
    default: bool,
    errors: list[str],
) -> bool:
    """Extract and validate an optional boolean field, collecting errors."""
    value = raw.get(key, default)
    if not isinstance(value, bool):
        errors.append(f"{key} must be a boolean, got {type(value).__name__}")
        return default
    return value


def _collect_int_min(  # noqa: PLR0913
    raw: dict[str, object],
    key: str,
    *,
    default: int,
    minimum: int,
    errors: list[str],
    min_error_suffix: str = "",
) -> int:
    """Extract and validate an optional integer field with a minimum bound, collecting errors."""
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{key} must be an integer, got {type(value).__name__}")
        return default
    if value < minimum:
        msg = f"{key} must be >= {minimum}, got {value}"
        if min_error_suffix:
            msg = f"{msg} {min_error_suffix}"
        errors.append(msg)
        return default
    return value


def _collect_choice(
    raw: dict[str, object],
    key: str,
    *,
    default: str,
    choices: frozenset[str],
    errors: list[str],
) -> str:
    """Extract and validate an optional string field against allowed values, collecting errors."""
    value = raw.get(key, default)
    if not isinstance(value, str):
        errors.append(f"{key} must be a string, got {type(value).__name__}")
        return default
    normalised = value.lower()
    if normalised not in choices:
        errors.append(f"{key} must be one of {sorted(choices)}, got {normalised!r}")
        return default
    return normalised


def _collect_base_url(
    raw: dict[str, object],
    errors: list[str],
) -> str:
    """Extract and validate the GitHub base URL, collecting errors."""
    value = raw.get("github_base_url", "https://api.github.com")
    if not isinstance(value, str):
        errors.append(f"github_base_url must be a string, got {type(value).__name__}")
        return "https://api.github.com"
    if not value.startswith(("http://", "https://")):
        errors.append(f"github_base_url must start with http:// or https://, got {value!r}")
        return "https://api.github.com"
    return value.rstrip("/")


def _collect_repos(
    raw: dict[str, object],
    errors: list[str],
) -> list[str]:
    """Extract and validate the repos list, collecting errors."""
    repos = raw.get("repos", [])
    if not isinstance(repos, list):
        errors.append("repos must be a list")
        return []
    has_error = False
    for repo in repos:
        if not isinstance(repo, str) or not _REPO_PATTERN.match(repo):
            errors.append(f"Invalid repo format: {repo!r} (expected 'owner/name') — example: 'octocat/Hello-World'")
            has_error = True
    return [] if has_error else repos


def _validate_repo_notification(
    repo_name: str,
    repo_raw: dict[str, object],
    errors: list[str],
) -> RepoNotificationConfig:
    """Validate a single ``[notifications.repos."owner/repo"]`` entry, collecting errors."""
    # Validate repo name format against the same pattern used for top-level repos.
    if not _REPO_PATTERN.match(repo_name):
        errors.append(
            f"Invalid repo format in [notifications.repos]: {repo_name!r}"
            " (expected 'owner/name') \N{EM DASH} example: 'octocat/Hello-World'"
        )

    enabled = repo_raw.get("enabled", True)
    if not isinstance(enabled, bool):
        errors.append(f"notifications.repos.{repo_name!r}.enabled must be a boolean, got {type(enabled).__name__}")
        enabled = True

    urgency: str | None = None
    urgency_raw = repo_raw.get("urgency")
    if urgency_raw is not None:
        if not isinstance(urgency_raw, str):
            errors.append(
                f"notifications.repos.{repo_name!r}.urgency must be a string, got {type(urgency_raw).__name__}"
            )
        else:
            urgency = urgency_raw.lower()
            if urgency not in _VALID_URGENCIES:
                errors.append(
                    f"notifications.repos.{repo_name!r}.urgency must be one of"
                    f" {sorted(_VALID_URGENCIES)}, got {urgency!r}"
                )
                urgency = None

    threshold: int | None = None
    threshold_raw = repo_raw.get("threshold")
    if threshold_raw is not None:
        if isinstance(threshold_raw, bool) or not isinstance(threshold_raw, int):
            errors.append(
                f"notifications.repos.{repo_name!r}.threshold must be an integer, got {type(threshold_raw).__name__}"
            )
        elif threshold_raw < 1:
            errors.append(f"notifications.repos.{repo_name!r}.threshold must be >= 1, got {threshold_raw}")
        else:
            threshold = threshold_raw

    return RepoNotificationConfig(enabled=enabled, urgency=urgency, threshold=threshold)


def _validate_notifications(raw: dict[str, object], errors: list[str]) -> NotificationConfig:
    """Validate the ``[notifications]`` section, collecting errors."""
    section = raw.get("notifications")
    if section is None:
        return NotificationConfig()

    if not isinstance(section, dict):
        errors.append("notifications must be a table")
        return NotificationConfig()

    raw_grouping = section.get("grouping", "flat")
    grouping = "flat"
    if not isinstance(raw_grouping, str):
        errors.append(f"notifications.grouping must be a string, got {type(raw_grouping).__name__}")
    else:
        grouping = raw_grouping.lower()
        if grouping not in _VALID_GROUPING_MODES:
            errors.append(f"notifications.grouping must be one of {sorted(_VALID_GROUPING_MODES)}, got {grouping!r}")
            grouping = "flat"

    repos_raw = section.get("repos", {})
    if not isinstance(repos_raw, dict):
        errors.append("notifications.repos must be a table")
        return NotificationConfig(grouping=grouping)

    repo_configs: dict[str, RepoNotificationConfig] = {}
    for repo_name, repo_raw in repos_raw.items():
        if not isinstance(repo_raw, dict):
            errors.append(f"notifications.repos.{repo_name!r} must be a table")
            continue
        repo_configs[repo_name] = _validate_repo_notification(repo_name, repo_raw, errors)

    return NotificationConfig(grouping=grouping, repos=repo_configs)


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def _validate(raw: dict[str, object]) -> Config:
    """Validate raw TOML dict and return a Config instance.

    Collects *all* validation errors and raises a single ``ConfigError``
    with every problem reported, so the user can fix everything in one pass.
    """
    errors: list[str] = []

    github_token = _collect_str(
        raw,
        "github_token",
        "github_token is required (set in config.toml or export GITHUB_TOKEN=ghp_...)",
        errors,
    )
    github_username = _collect_str(
        raw,
        "github_username",
        "github_username is required",
        errors,
    )

    poll_interval = _collect_int_min(
        raw,
        "poll_interval",
        default=300,
        minimum=_MIN_POLL_INTERVAL,
        errors=errors,
        min_error_suffix="(GitHub recommends 300s for personal tokens)",
    )

    repos = _collect_repos(raw, errors)
    log_level = _collect_choice(raw, "log_level", default="info", choices=_VALID_LOG_LEVELS, errors=errors)
    notify_on_first_poll = _collect_bool(raw, "notify_on_first_poll", default=False, errors=errors)
    notifications_enabled = _collect_bool(raw, "notifications_enabled", default=True, errors=errors)
    dbus_enabled = _collect_bool(raw, "dbus_enabled", default=True, errors=errors)
    github_base_url = _collect_base_url(raw, errors)
    max_retries = _collect_int_min(raw, "max_retries", default=3, minimum=0, errors=errors)
    notification_threshold = _collect_int_min(raw, "notification_threshold", default=3, minimum=1, errors=errors)
    notification_urgency = _collect_choice(
        raw,
        "notification_urgency",
        default="normal",
        choices=_VALID_URGENCIES,
        errors=errors,
    )
    icon_theme = _collect_choice(raw, "icon_theme", default="light", choices=_VALID_ICON_THEMES, errors=errors)

    # Notifications section is validated into the same error list so that
    # notification errors are reported together with top-level errors.
    notifications = _validate_notifications(raw, errors)

    if errors:
        msg = "\n".join(errors)
        raise ConfigError(msg)

    return Config(
        github_token=github_token,
        github_username=github_username,
        poll_interval=poll_interval,
        repos=repos,
        log_level=log_level,
        notify_on_first_poll=notify_on_first_poll,
        notifications_enabled=notifications_enabled,
        dbus_enabled=dbus_enabled,
        github_base_url=github_base_url,
        max_retries=max_retries,
        notification_threshold=notification_threshold,
        notification_urgency=notification_urgency,
        icon_theme=icon_theme,
        notifications=notifications,
    )

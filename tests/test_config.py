"""Tests for github_monitor.config."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from github_monitor.config import Config, ConfigError, load_config

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_TOML = """\
github_token = "ghp_test1234567890"
github_username = "testuser"
poll_interval = 60
repos = ["owner/repo1", "org/repo2"]
"""

MINIMAL_TOML = """\
github_token = "ghp_test1234567890"
github_username = "testuser"
"""


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Write a valid config and return its path."""
    p = tmp_path / "config.toml"
    p.write_text(VALID_TOML)
    return p


@pytest.fixture
def minimal_config_file(tmp_path: Path) -> Path:
    """Write a minimal config (only required fields) and return its path."""
    p = tmp_path / "config.toml"
    p.write_text(MINIMAL_TOML)
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_valid_config(config_file: Path) -> None:
    cfg = load_config(config_file)
    assert cfg.github_token == "ghp_test1234567890"
    assert cfg.github_username == "testuser"
    assert cfg.poll_interval == 60
    assert cfg.repos == ["owner/repo1", "org/repo2"]


def test_load_minimal_config_uses_defaults(minimal_config_file: Path) -> None:
    cfg = load_config(minimal_config_file)
    assert cfg.poll_interval == 300
    assert cfg.repos == []


def test_config_path_as_string(config_file: Path) -> None:
    cfg = load_config(str(config_file))
    assert isinstance(cfg, Config)


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


def test_env_github_token_overrides_file(
    config_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    cfg = load_config(config_file)
    assert cfg.github_token == "ghp_from_env"


def test_env_github_monitor_config_path(
    config_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_MONITOR_CONFIG", str(config_file))
    # Call without explicit path — should pick up env var
    cfg = load_config()
    assert cfg.github_username == "testuser"


def test_env_token_provides_missing_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config file without token + GITHUB_TOKEN env var should succeed."""
    p = tmp_path / "config.toml"
    p.write_text('github_username = "testuser"\n')
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    cfg = load_config(p)
    assert cfg.github_token == "ghp_from_env"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path / "nonexistent.toml")


def test_invalid_toml(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("this is [not valid toml =")
    with pytest.raises(ConfigError, match="Invalid TOML"):
        load_config(p)


def test_missing_token(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_username = "testuser"\n')
    with pytest.raises(ConfigError, match="github_token is required"):
        load_config(p)


def test_missing_username(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = "ghp_abc"\n')
    with pytest.raises(ConfigError, match="github_username is required"):
        load_config(p)


def test_poll_interval_too_low(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = "ghp_abc"\ngithub_username = "user"\npoll_interval = 10\n')
    with pytest.raises(ConfigError, match="poll_interval must be >= 30"):
        load_config(p)


def test_poll_interval_wrong_type(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = "ghp_abc"\ngithub_username = "user"\npoll_interval = "fast"\n')
    with pytest.raises(ConfigError, match="poll_interval must be an integer"):
        load_config(p)


def test_invalid_repo_format(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = "ghp_abc"\ngithub_username = "user"\nrepos = ["not-a-valid-repo"]\n')
    with pytest.raises(ConfigError, match="Invalid repo format"):
        load_config(p)


def test_repos_not_a_list(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = "ghp_abc"\ngithub_username = "user"\nrepos = "owner/repo"\n')
    with pytest.raises(ConfigError, match="repos must be a list"):
        load_config(p)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_token_string(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = ""\ngithub_username = "user"\n')
    with pytest.raises(ConfigError, match="github_token is required"):
        load_config(p)


def test_empty_username_string(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('github_token = "ghp_abc"\ngithub_username = ""\n')
    with pytest.raises(ConfigError, match="github_username is required"):
        load_config(p)


def test_poll_interval_at_boundary(tmp_path: Path) -> None:
    """poll_interval = 30 should be accepted (minimum allowed)."""
    p = tmp_path / "config.toml"
    p.write_text('github_token = "ghp_abc"\ngithub_username = "user"\npoll_interval = 30\n')
    cfg = load_config(p)
    assert cfg.poll_interval == 30

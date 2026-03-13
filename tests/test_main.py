"""Tests for forgewatch.__main__."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgewatch.__main__ import build_full_parser, main
from forgewatch.config import Config, ConfigError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> Config:
    """Build a Config with sensible test defaults."""
    return Config(
        github_token="ghp_test1234567890",
        github_username="testuser",
        poll_interval=300,
        repos=[],
    )


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------


class TestMainHappyPath:
    """main() should load config, create daemon, and run it."""

    def test_runs_daemon(self) -> None:
        config = _make_config()
        mock_daemon_instance = MagicMock()
        mock_daemon_instance.start = AsyncMock()
        mock_daemon_instance.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config) as mock_load,
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon_instance) as mock_daemon_cls,
            patch("sys.argv", ["forgewatch"]),
        ):
            main()

        mock_load.assert_called_once_with(None)
        mock_daemon_cls.assert_called_once_with(config, None)
        mock_daemon_instance.start.assert_awaited_once()
        mock_daemon_instance.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: config flag
# ---------------------------------------------------------------------------


class TestMainConfigFlag:
    """The -c / --config flag should be forwarded to load_config."""

    def test_config_short_flag(self) -> None:
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock()
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config) as mock_load,
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch", "-c", "/opt/ghm/config.toml"]),
        ):
            main()

        mock_load.assert_called_once_with(Path("/opt/ghm/config.toml"))

    def test_config_long_flag(self) -> None:
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock()
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config) as mock_load,
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch", "--config", "/etc/ghm.toml"]),
        ):
            main()

        mock_load.assert_called_once_with(Path("/etc/ghm.toml"))


# ---------------------------------------------------------------------------
# Tests: verbose flag
# ---------------------------------------------------------------------------


class TestMainVerboseFlag:
    """The -v / --verbose flag should set logging to DEBUG."""

    def test_verbose_enables_debug(self) -> None:
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock()
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config),
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch", "-v"]),
            patch("logging.basicConfig") as mock_basic_config,
        ):
            main()

        mock_basic_config.assert_called_once()
        call_kwargs: dict[str, Any] = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.DEBUG

    def test_default_log_level_is_info(self) -> None:
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock()
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config),
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch"]),
            patch("logging.basicConfig") as mock_basic_config,
        ):
            main()

        call_kwargs: dict[str, Any] = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.INFO


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


class TestMainErrorHandling:
    """Config errors should be caught and produce clean exits."""

    def test_missing_config_exits_with_setup_hint(self, caplog: pytest.LogCaptureFixture) -> None:
        """Missing config file should exit cleanly and suggest 'forgewatch setup'."""
        with (
            patch(
                "forgewatch.config.load_config", side_effect=ConfigError("Config file not found: /missing/config.toml")
            ),
            patch("sys.argv", ["forgewatch"]),
            caplog.at_level(logging.ERROR),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

        # Should mention the setup command
        assert any("forgewatch setup" in record.message for record in caplog.records)
        # Should not produce a raw traceback (ConfigError is caught)

    def test_invalid_config_exits_with_check_hint(self, caplog: pytest.LogCaptureFixture) -> None:
        """Invalid config should exit cleanly and suggest checking config."""
        with (
            patch("forgewatch.config.load_config", side_effect=ConfigError("github_token is required")),
            patch("sys.argv", ["forgewatch"]),
            caplog.at_level(logging.ERROR),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

        # Should mention checking the config file
        assert any("check your config file" in record.message.lower() for record in caplog.records)

    def test_config_error_exits_code_1(self) -> None:
        """Any ConfigError should result in exit code 1."""
        with (
            patch("forgewatch.config.load_config", side_effect=ConfigError("some error")),
            patch("sys.argv", ["forgewatch"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_stop_called_even_on_start_failure(self) -> None:
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock(side_effect=RuntimeError("dbus failed"))
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config),
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch"]),
            pytest.raises(RuntimeError, match="dbus failed"),
        ):
            main()

        # stop() should still be called via finally
        mock_daemon.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: CLI subcommand dispatch (Step 10/11)
# ---------------------------------------------------------------------------


class TestCliDispatch:
    """main() should dispatch to cli.dispatch for known subcommands."""

    def test_unified_help_includes_subcommands(self) -> None:
        """--help output should mention all management subcommands."""
        parser = build_full_parser()
        help_text = parser.format_help()
        assert "setup" in help_text
        assert "service" in help_text
        assert "uninstall" in help_text

    def test_unified_help_includes_daemon_flags(self) -> None:
        parser = build_full_parser()
        help_text = parser.format_help()
        assert "--config" in help_text
        assert "--verbose" in help_text

    @patch("forgewatch.cli.dispatch")
    def test_dispatches_setup(self, mock_dispatch: MagicMock) -> None:
        with patch("sys.argv", ["forgewatch", "setup"]):
            main()
        mock_dispatch.assert_called_once()
        assert mock_dispatch.call_args[0][0].command == "setup"

    @patch("forgewatch.cli.dispatch")
    def test_dispatches_service(self, mock_dispatch: MagicMock) -> None:
        with patch("sys.argv", ["forgewatch", "service", "status"]):
            main()
        mock_dispatch.assert_called_once()
        args = mock_dispatch.call_args[0][0]
        assert args.command == "service"
        assert args.action == "status"

    @patch("forgewatch.cli.dispatch")
    def test_dispatches_uninstall(self, mock_dispatch: MagicMock) -> None:
        with patch("sys.argv", ["forgewatch", "uninstall"]):
            main()
        mock_dispatch.assert_called_once()
        assert mock_dispatch.call_args[0][0].command == "uninstall"

    @patch("forgewatch.cli.dispatch")
    def test_does_not_dispatch_for_daemon_flags(self, mock_dispatch: MagicMock) -> None:
        """Daemon flags like -c and -v should NOT trigger CLI dispatch."""
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock()
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config),
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch", "-c", "config.toml"]),
        ):
            main()

        mock_dispatch.assert_not_called()

    @patch("forgewatch.cli.dispatch")
    def test_does_not_dispatch_for_no_args(self, mock_dispatch: MagicMock) -> None:
        """No arguments should run the daemon, not the CLI."""
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock()
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config),
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch"]),
        ):
            main()

        mock_dispatch.assert_not_called()

    @patch("forgewatch.cli.dispatch")
    def test_does_not_dispatch_for_verbose_flag(self, mock_dispatch: MagicMock) -> None:
        """The -v flag should run the daemon, not the CLI."""
        config = _make_config()
        mock_daemon = MagicMock()
        mock_daemon.start = AsyncMock()
        mock_daemon.stop = AsyncMock()

        with (
            patch("forgewatch.config.load_config", return_value=config),
            patch("forgewatch.daemon.Daemon", return_value=mock_daemon),
            patch("sys.argv", ["forgewatch", "-v"]),
        ):
            main()

        mock_dispatch.assert_not_called()

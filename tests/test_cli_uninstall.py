"""Tests for github_monitor.cli.uninstall."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from github_monitor.cli.uninstall import (
    _print_summary,
    _remove_config,
    _stop_daemon,
    _stop_indicator,
    run_uninstall,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


# ---------------------------------------------------------------------------
# _stop_indicator — stop + disable the indicator service
# ---------------------------------------------------------------------------


class TestStopIndicator:
    """Verify indicator stop/disable logic."""

    @patch("github_monitor.cli.uninstall._systemd")
    def test_stops_and_disables_when_active_and_enabled(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = True
        mock_systemd.is_enabled.return_value = True
        _stop_indicator()
        mock_systemd.stop.assert_called_once_with(mock_systemd.INDICATOR_SERVICE)
        mock_systemd.disable.assert_called_once_with(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.uninstall._systemd")
    def test_skips_stop_when_inactive(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = False
        mock_systemd.is_enabled.return_value = True
        _stop_indicator()
        mock_systemd.stop.assert_not_called()
        mock_systemd.disable.assert_called_once_with(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.uninstall._systemd")
    def test_skips_disable_when_not_enabled(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = True
        mock_systemd.is_enabled.return_value = False
        _stop_indicator()
        mock_systemd.stop.assert_called_once_with(mock_systemd.INDICATOR_SERVICE)
        mock_systemd.disable.assert_not_called()

    @patch("github_monitor.cli.uninstall._systemd")
    def test_does_nothing_when_inactive_and_not_enabled(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = False
        mock_systemd.is_enabled.return_value = False
        _stop_indicator()
        mock_systemd.stop.assert_not_called()
        mock_systemd.disable.assert_not_called()


# ---------------------------------------------------------------------------
# _stop_daemon — stop + disable the daemon service
# ---------------------------------------------------------------------------


class TestStopDaemon:
    """Verify daemon stop/disable logic."""

    @patch("github_monitor.cli.uninstall._systemd")
    def test_stops_and_disables_when_active_and_enabled(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = True
        mock_systemd.is_enabled.return_value = True
        _stop_daemon()
        mock_systemd.stop.assert_called_once_with(mock_systemd.DAEMON_SERVICE)
        mock_systemd.disable.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.uninstall._systemd")
    def test_skips_stop_when_inactive(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = False
        mock_systemd.is_enabled.return_value = True
        _stop_daemon()
        mock_systemd.stop.assert_not_called()
        mock_systemd.disable.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.uninstall._systemd")
    def test_skips_disable_when_not_enabled(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = True
        mock_systemd.is_enabled.return_value = False
        _stop_daemon()
        mock_systemd.stop.assert_called_once_with(mock_systemd.DAEMON_SERVICE)
        mock_systemd.disable.assert_not_called()

    @patch("github_monitor.cli.uninstall._systemd")
    def test_does_nothing_when_inactive_and_not_enabled(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = False
        mock_systemd.is_enabled.return_value = False
        _stop_daemon()
        mock_systemd.stop.assert_not_called()
        mock_systemd.disable.assert_not_called()


# ---------------------------------------------------------------------------
# _remove_config — optional config directory removal
# ---------------------------------------------------------------------------


class TestRemoveConfig:
    """Verify config removal prompt and behaviour."""

    def test_removes_when_user_says_yes(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text("token = abc")

        with (
            patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.uninstall.ask_yes_no", return_value=True),
        ):
            _remove_config()

        assert not config_dir.exists()

    def test_preserves_when_user_says_no(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text("token = abc")

        with (
            patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.uninstall.ask_yes_no", return_value=False),
        ):
            _remove_config()

        assert config_dir.exists()
        assert (config_dir / "config.toml").exists()

    def test_handles_missing_config_dir(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "nonexistent"

        with (
            patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.uninstall.ask_yes_no") as mock_ask,
        ):
            _remove_config()  # should not raise

        # Should not prompt when directory doesn't exist
        mock_ask.assert_not_called()

    def test_prompt_defaults_to_no(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_dir.mkdir()

        with (
            patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.uninstall.ask_yes_no", return_value=False) as mock_ask,
        ):
            _remove_config()

        mock_ask.assert_called_once()
        # Verify default=False is passed
        assert mock_ask.call_args[1]["default"] is False


# ---------------------------------------------------------------------------
# _print_summary — final output
# ---------------------------------------------------------------------------


class TestPrintSummary:
    """Verify uninstall summary output."""

    def test_includes_complete_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_dir = tmp_path / "nonexistent"
        with patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir):
            _print_summary()
        output = capsys.readouterr().out
        assert "Uninstall complete!" in output

    def test_shows_pip_uninstall_hint(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_dir = tmp_path / "nonexistent"
        with patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir):
            _print_summary()
        output = capsys.readouterr().out
        assert "pip uninstall github-monitor" in output

    def test_shows_config_path_when_preserved(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_dir = tmp_path / "github-monitor"
        config_dir.mkdir()
        with patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir):
            _print_summary()
        output = capsys.readouterr().out
        assert str(config_dir) in output
        assert "preserved" in output

    def test_no_config_reminder_when_removed(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_dir = tmp_path / "nonexistent"
        with patch("github_monitor.cli.uninstall.CONFIG_DIR", config_dir):
            _print_summary()
        output = capsys.readouterr().out
        assert "preserved" not in output


# ---------------------------------------------------------------------------
# run_uninstall — full flow
# ---------------------------------------------------------------------------


class TestRunUninstall:
    """Verify the full uninstall flow."""

    @patch("github_monitor.cli.uninstall._print_summary")
    @patch("github_monitor.cli.uninstall._remove_config")
    @patch("github_monitor.cli.uninstall._systemd")
    @patch("github_monitor.cli.uninstall._stop_daemon")
    @patch("github_monitor.cli.uninstall._stop_indicator")
    @patch("github_monitor.cli.uninstall.check_systemctl", return_value=True)
    def test_full_flow_calls_all_steps(
        self,
        mock_check: MagicMock,
        mock_stop_indicator: MagicMock,
        mock_stop_daemon: MagicMock,
        mock_systemd: MagicMock,
        mock_remove_config: MagicMock,
        mock_summary: MagicMock,
    ) -> None:
        run_uninstall()

        mock_check.assert_called_once()
        mock_stop_indicator.assert_called_once()
        mock_stop_daemon.assert_called_once()
        mock_systemd.remove_service_files.assert_called_once()
        mock_systemd.remove_legacy_autostart.assert_called_once()
        mock_remove_config.assert_called_once()
        mock_summary.assert_called_once()

    @patch("github_monitor.cli.uninstall._print_summary")
    @patch("github_monitor.cli.uninstall._remove_config")
    @patch("github_monitor.cli.uninstall._systemd")
    @patch("github_monitor.cli.uninstall._stop_daemon")
    @patch("github_monitor.cli.uninstall._stop_indicator")
    @patch("github_monitor.cli.uninstall.check_systemctl", return_value=True)
    def test_stops_indicator_before_daemon(
        self,
        mock_check: MagicMock,
        mock_stop_indicator: MagicMock,
        mock_stop_daemon: MagicMock,
        mock_systemd: MagicMock,
        mock_remove_config: MagicMock,
        mock_summary: MagicMock,
    ) -> None:
        """Indicator must be stopped before the daemon (reverse dependency order)."""
        call_order: list[str] = []
        mock_stop_indicator.side_effect = lambda: call_order.append("indicator")
        mock_stop_daemon.side_effect = lambda: call_order.append("daemon")

        run_uninstall()

        assert call_order == ["indicator", "daemon"]

    @patch("github_monitor.cli.uninstall._print_summary")
    @patch("github_monitor.cli.uninstall._remove_config")
    @patch("github_monitor.cli.uninstall._systemd")
    @patch("github_monitor.cli.uninstall._stop_daemon")
    @patch("github_monitor.cli.uninstall._stop_indicator")
    @patch("github_monitor.cli.uninstall.check_systemctl", return_value=False)
    def test_skips_stop_when_no_systemctl(
        self,
        mock_check: MagicMock,
        mock_stop_indicator: MagicMock,
        mock_stop_daemon: MagicMock,
        mock_systemd: MagicMock,
        mock_remove_config: MagicMock,
        mock_summary: MagicMock,
    ) -> None:
        run_uninstall()

        # Stop/disable skipped
        mock_stop_indicator.assert_not_called()
        mock_stop_daemon.assert_not_called()

        # File removal still happens
        mock_systemd.remove_service_files.assert_called_once()
        mock_systemd.remove_legacy_autostart.assert_called_once()

        # Config prompt and summary still run
        mock_remove_config.assert_called_once()
        mock_summary.assert_called_once()

    @patch("github_monitor.cli.uninstall._print_summary")
    @patch("github_monitor.cli.uninstall._remove_config")
    @patch("github_monitor.cli.uninstall._systemd")
    @patch("github_monitor.cli.uninstall._stop_daemon")
    @patch("github_monitor.cli.uninstall._stop_indicator")
    @patch("github_monitor.cli.uninstall.check_systemctl", return_value=False)
    def test_no_systemctl_still_removes_legacy_autostart(
        self,
        mock_check: MagicMock,
        mock_stop_indicator: MagicMock,
        mock_stop_daemon: MagicMock,
        mock_systemd: MagicMock,
        mock_remove_config: MagicMock,
        mock_summary: MagicMock,
    ) -> None:
        run_uninstall()
        mock_systemd.remove_legacy_autostart.assert_called_once()

    def test_banner_is_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("github_monitor.cli.uninstall._print_summary"),
            patch("github_monitor.cli.uninstall._remove_config"),
            patch("github_monitor.cli.uninstall._systemd"),
            patch("github_monitor.cli.uninstall._stop_daemon"),
            patch("github_monitor.cli.uninstall._stop_indicator"),
            patch("github_monitor.cli.uninstall.check_systemctl", return_value=False),
        ):
            run_uninstall()
        output = capsys.readouterr().out
        assert "GitHub Monitor Uninstall" in output

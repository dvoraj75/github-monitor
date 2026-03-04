"""Tests for github_monitor.cli.service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from github_monitor.cli.service import (
    _action_disable,
    _action_enable,
    _action_install,
    _action_restart,
    _action_start,
    _action_status,
    _action_stop,
    _has_indicator,
    _require_systemctl,
    run_service,
)

# ---------------------------------------------------------------------------
# _require_systemctl — pre-flight gate
# ---------------------------------------------------------------------------


class TestRequireSystemctl:
    """Verify the systemctl availability check."""

    @patch("github_monitor.cli.service._checks")
    def test_returns_true_when_available(self, mock_checks: MagicMock) -> None:
        mock_checks.check_systemctl.return_value = True
        assert _require_systemctl() is True

    @patch("github_monitor.cli.service._checks")
    @patch("github_monitor.cli.service.err")
    def test_returns_false_when_missing(self, mock_err: MagicMock, mock_checks: MagicMock) -> None:
        mock_checks.check_systemctl.return_value = False
        assert _require_systemctl() is False

    @patch("github_monitor.cli.service._checks")
    @patch("github_monitor.cli.service.err")
    def test_prints_error_when_missing(self, mock_err: MagicMock, mock_checks: MagicMock) -> None:
        mock_checks.check_systemctl.return_value = False
        _require_systemctl()
        mock_err.assert_called_once()
        assert "systemctl" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# _has_indicator — checks if indicator service file exists
# ---------------------------------------------------------------------------


class TestHasIndicator:
    """Verify indicator service file detection."""

    @patch("github_monitor.cli.service._systemd")
    def test_returns_true_when_installed(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        assert _has_indicator() is True
        mock_systemd.service_file_installed.assert_called_once_with(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_returns_false_when_missing(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = False
        assert _has_indicator() is False


# ---------------------------------------------------------------------------
# run_service — dispatch + systemctl gate
# ---------------------------------------------------------------------------


class TestRunService:
    """Verify dispatch logic and systemctl pre-flight check."""

    @patch("github_monitor.cli.service._checks")
    def test_exits_when_systemctl_missing(self, mock_checks: MagicMock) -> None:
        mock_checks.check_systemctl.return_value = False
        with (
            patch("github_monitor.cli.service.err"),
            pytest.raises(SystemExit, match="1"),
        ):
            run_service("start")

    @patch("github_monitor.cli.service._checks")
    @patch("github_monitor.cli.service._systemd")
    def test_dispatches_valid_action(self, mock_systemd: MagicMock, mock_checks: MagicMock) -> None:
        mock_checks.check_systemctl.return_value = True
        mock_systemd.service_file_installed.return_value = False
        run_service("start")
        mock_systemd.start.assert_called_once()

    @patch("github_monitor.cli.service._checks")
    def test_exits_on_unknown_action(self, mock_checks: MagicMock) -> None:
        mock_checks.check_systemctl.return_value = True
        with (
            patch("github_monitor.cli.service.err") as mock_err,
            pytest.raises(SystemExit, match="1"),
        ):
            run_service("bogus")
        assert "Unknown" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# install action
# ---------------------------------------------------------------------------


class TestActionInstall:
    """Verify the 'install' action."""

    @patch("github_monitor.cli.service._systemd")
    @patch("github_monitor.cli.service._checks")
    def test_install_with_gtk(self, mock_checks: MagicMock, mock_systemd: MagicMock) -> None:
        mock_checks.check_gtk_indicator.return_value = True
        _action_install()
        mock_systemd.install_service_files.assert_called_once_with(include_indicator=True)

    @patch("github_monitor.cli.service._systemd")
    @patch("github_monitor.cli.service._checks")
    def test_install_without_gtk(self, mock_checks: MagicMock, mock_systemd: MagicMock) -> None:
        mock_checks.check_gtk_indicator.return_value = False
        _action_install()
        mock_systemd.install_service_files.assert_called_once_with(include_indicator=False)


# ---------------------------------------------------------------------------
# start action
# ---------------------------------------------------------------------------


class TestActionStart:
    """Verify the 'start' action."""

    @patch("github_monitor.cli.service._systemd")
    def test_start_daemon_only(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = False
        _action_start()
        mock_systemd.start.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_start_daemon_and_indicator(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        _action_start()
        assert mock_systemd.start.call_count == 2
        mock_systemd.start.assert_any_call(mock_systemd.DAEMON_SERVICE)
        mock_systemd.start.assert_any_call(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_start_daemon_before_indicator(self, mock_systemd: MagicMock) -> None:
        """Daemon must be started before the indicator (dependency order)."""
        mock_systemd.service_file_installed.return_value = True
        calls: list[str] = []
        mock_systemd.start.side_effect = calls.append
        _action_start()
        assert calls == [mock_systemd.DAEMON_SERVICE, mock_systemd.INDICATOR_SERVICE]


# ---------------------------------------------------------------------------
# stop action
# ---------------------------------------------------------------------------


class TestActionStop:
    """Verify the 'stop' action."""

    @patch("github_monitor.cli.service._systemd")
    def test_stop_daemon_only_no_indicator(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = False
        _action_stop()
        mock_systemd.stop.assert_called_once_with(mock_systemd.DAEMON_SERVICE)
        mock_systemd.is_active.assert_not_called()

    @patch("github_monitor.cli.service._systemd")
    def test_stop_both_when_indicator_active(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        mock_systemd.is_active.return_value = True
        _action_stop()
        assert mock_systemd.stop.call_count == 2
        mock_systemd.stop.assert_any_call(mock_systemd.INDICATOR_SERVICE)
        mock_systemd.stop.assert_any_call(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_stop_indicator_before_daemon(self, mock_systemd: MagicMock) -> None:
        """Indicator must be stopped before the daemon (reverse dependency order)."""
        mock_systemd.service_file_installed.return_value = True
        mock_systemd.is_active.return_value = True
        calls: list[str] = []
        mock_systemd.stop.side_effect = calls.append
        _action_stop()
        assert calls == [mock_systemd.INDICATOR_SERVICE, mock_systemd.DAEMON_SERVICE]

    @patch("github_monitor.cli.service._systemd")
    def test_stop_skips_indicator_when_inactive(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        mock_systemd.is_active.return_value = False
        _action_stop()
        mock_systemd.stop.assert_called_once_with(mock_systemd.DAEMON_SERVICE)


# ---------------------------------------------------------------------------
# restart action
# ---------------------------------------------------------------------------


class TestActionRestart:
    """Verify the 'restart' action."""

    @patch("github_monitor.cli.service._systemd")
    def test_restart_daemon_only_no_indicator(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = False
        _action_restart()
        mock_systemd.restart.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_restart_both_when_indicator_active(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        mock_systemd.is_active.return_value = True
        _action_restart()
        assert mock_systemd.restart.call_count == 2
        mock_systemd.restart.assert_any_call(mock_systemd.DAEMON_SERVICE)
        mock_systemd.restart.assert_any_call(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_restart_daemon_before_indicator(self, mock_systemd: MagicMock) -> None:
        """Daemon must be restarted before the indicator."""
        mock_systemd.service_file_installed.return_value = True
        mock_systemd.is_active.return_value = True
        calls: list[str] = []
        mock_systemd.restart.side_effect = calls.append
        _action_restart()
        assert calls == [mock_systemd.DAEMON_SERVICE, mock_systemd.INDICATOR_SERVICE]

    @patch("github_monitor.cli.service._systemd")
    def test_restart_skips_indicator_when_inactive(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        mock_systemd.is_active.return_value = False
        _action_restart()
        mock_systemd.restart.assert_called_once_with(mock_systemd.DAEMON_SERVICE)


# ---------------------------------------------------------------------------
# status action
# ---------------------------------------------------------------------------


class TestActionStatus:
    """Verify the 'status' action."""

    @patch("github_monitor.cli.service._systemd")
    def test_status_daemon_only(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = False
        _action_status()
        mock_systemd.print_status.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_status_both_when_indicator_installed(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        _action_status()
        assert mock_systemd.print_status.call_count == 2
        mock_systemd.print_status.assert_any_call(mock_systemd.DAEMON_SERVICE)
        mock_systemd.print_status.assert_any_call(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_status_prints_separator_between_services(
        self, mock_systemd: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_systemd.service_file_installed.return_value = True
        _action_status()
        output = capsys.readouterr().out
        assert "\n" in output


# ---------------------------------------------------------------------------
# enable action
# ---------------------------------------------------------------------------


class TestActionEnable:
    """Verify the 'enable' action."""

    @patch("github_monitor.cli.service._systemd")
    def test_enable_daemon_only(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = False
        _action_enable()
        mock_systemd.enable.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_enable_daemon_and_indicator(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        _action_enable()
        assert mock_systemd.enable.call_count == 2
        mock_systemd.enable.assert_any_call(mock_systemd.DAEMON_SERVICE)
        mock_systemd.enable.assert_any_call(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_enable_daemon_before_indicator(self, mock_systemd: MagicMock) -> None:
        """Daemon must be enabled before the indicator."""
        mock_systemd.service_file_installed.return_value = True
        calls: list[str] = []
        mock_systemd.enable.side_effect = calls.append
        _action_enable()
        assert calls == [mock_systemd.DAEMON_SERVICE, mock_systemd.INDICATOR_SERVICE]


# ---------------------------------------------------------------------------
# disable action
# ---------------------------------------------------------------------------


class TestActionDisable:
    """Verify the 'disable' action."""

    @patch("github_monitor.cli.service._systemd")
    def test_disable_daemon_only_no_indicator(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = False
        _action_disable()
        mock_systemd.disable.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_disable_both_when_indicator_installed(self, mock_systemd: MagicMock) -> None:
        mock_systemd.service_file_installed.return_value = True
        _action_disable()
        assert mock_systemd.disable.call_count == 2
        mock_systemd.disable.assert_any_call(mock_systemd.INDICATOR_SERVICE)
        mock_systemd.disable.assert_any_call(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.service._systemd")
    def test_disable_indicator_before_daemon(self, mock_systemd: MagicMock) -> None:
        """Indicator must be disabled before the daemon (reverse dependency order)."""
        mock_systemd.service_file_installed.return_value = True
        calls: list[str] = []
        mock_systemd.disable.side_effect = calls.append
        _action_disable()
        assert calls == [mock_systemd.INDICATOR_SERVICE, mock_systemd.DAEMON_SERVICE]

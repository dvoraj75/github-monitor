"""Tests for github_monitor.cli._systemd."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from github_monitor.cli._systemd import (
    DAEMON_SERVICE,
    INDICATOR_SERVICE,
    _read_service_file,
    _resolve_exec,
    _run_systemctl,
    daemon_reload,
    disable,
    enable,
    install_service_files,
    is_active,
    is_enabled,
    print_status,
    remove_legacy_autostart,
    remove_service_files,
    restart,
    service_file_installed,
    start,
    stop,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(returncode: int = 0) -> subprocess.CompletedProcess[bytes]:
    """Build a CompletedProcess with the given return code."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=b"", stderr=b"")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants."""

    def test_daemon_service_name(self) -> None:
        assert DAEMON_SERVICE == "github-monitor.service"

    def test_indicator_service_name(self) -> None:
        assert INDICATOR_SERVICE == "github-monitor-indicator.service"


# ---------------------------------------------------------------------------
# _read_service_file — reads bundled service files
# ---------------------------------------------------------------------------


class TestReadServiceFile:
    """Tests for _read_service_file()."""

    def test_reads_daemon_service(self) -> None:
        content = _read_service_file(DAEMON_SERVICE)
        assert "[Unit]" in content
        assert "GitHub PR Monitor" in content
        assert "[Service]" in content
        assert "[Install]" in content
        assert "@@GITHUB_MONITOR_EXEC@@" in content

    def test_reads_indicator_service(self) -> None:
        content = _read_service_file(INDICATOR_SERVICE)
        assert "[Unit]" in content
        assert "Indicator" in content
        assert "[Service]" in content
        assert "[Install]" in content
        assert "@@GITHUB_MONITOR_INDICATOR_EXEC@@" in content


# ---------------------------------------------------------------------------
# _run_systemctl — subprocess wrapper
# ---------------------------------------------------------------------------


class TestRunSystemctl:
    """Tests for _run_systemctl()."""

    def test_calls_systemctl_with_user_flag(self) -> None:
        with patch("github_monitor.cli._systemd.subprocess.run", return_value=_make_completed_process()) as mock_run:
            _run_systemctl("daemon-reload")
        mock_run.assert_called_once_with(
            ["systemctl", "--user", "daemon-reload"],
            check=False,
            capture_output=True,
        )

    def test_passes_additional_args(self) -> None:
        with patch("github_monitor.cli._systemd.subprocess.run", return_value=_make_completed_process()) as mock_run:
            _run_systemctl("is-active", "--quiet", "github-monitor.service")
        mock_run.assert_called_once_with(
            ["systemctl", "--user", "is-active", "--quiet", "github-monitor.service"],
            check=False,
            capture_output=True,
        )


# ---------------------------------------------------------------------------
# _resolve_exec — finds executable path on PATH
# ---------------------------------------------------------------------------


class TestResolveExec:
    """Tests for _resolve_exec()."""

    def test_returns_resolved_path(self) -> None:
        with patch("github_monitor.cli._systemd.shutil.which", return_value="/usr/local/bin/github-monitor"):
            result = _resolve_exec("github-monitor")
        assert result == "/usr/local/bin/github-monitor"

    def test_resolves_symlinks(self, tmp_path: Path) -> None:
        real = tmp_path / "real-binary"
        real.touch()
        link = tmp_path / "link-binary"
        link.symlink_to(real)
        with patch("github_monitor.cli._systemd.shutil.which", return_value=str(link)):
            result = _resolve_exec("github-monitor")
        assert result == str(real)

    def test_raises_when_not_found(self) -> None:
        with (
            patch("github_monitor.cli._systemd.shutil.which", return_value=None),
            pytest.raises(FileNotFoundError, match="Could not find 'no-such-binary'"),
        ):
            _resolve_exec("no-such-binary")


# ---------------------------------------------------------------------------
# install_service_files — writes service files to disk
# ---------------------------------------------------------------------------


class TestInstallServiceFiles:
    """Tests for install_service_files() using tmp_path for real file I/O."""

    def test_installs_daemon_service_only(self, tmp_path: Path) -> None:
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()

        daemon_file = tmp_path / DAEMON_SERVICE
        assert daemon_file.exists()
        content = daemon_file.read_text()
        assert "[Unit]" in content
        # Indicator should NOT be written
        assert not (tmp_path / INDICATOR_SERVICE).exists()

    def test_installs_both_services_when_indicator_requested(self, tmp_path: Path) -> None:
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch(
                "github_monitor.cli._systemd._resolve_exec",
                side_effect=lambda name: f"/venv/bin/{name}",
            ),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files(include_indicator=True)

        assert (tmp_path / DAEMON_SERVICE).exists()
        assert (tmp_path / INDICATOR_SERVICE).exists()

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "dir"
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", target),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()
        assert target.exists()
        assert (target / DAEMON_SERVICE).exists()

    def test_calls_daemon_reload_after_install(self, tmp_path: Path) -> None:
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload") as mock_reload,
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()
        mock_reload.assert_called_once()

    def test_prints_ok_for_each_installed_file(self, tmp_path: Path) -> None:
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch(
                "github_monitor.cli._systemd._resolve_exec",
                side_effect=lambda name: f"/venv/bin/{name}",
            ),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            install_service_files(include_indicator=True)
        assert mock_ok.call_count == 2
        messages = [c[0][0] for c in mock_ok.call_args_list]
        assert any(DAEMON_SERVICE in m for m in messages)
        assert any(INDICATOR_SERVICE in m for m in messages)

    def test_overwrites_existing_service_file(self, tmp_path: Path) -> None:
        (tmp_path / DAEMON_SERVICE).write_text("old content")
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()
        content = (tmp_path / DAEMON_SERVICE).read_text()
        assert content != "old content"
        assert "[Unit]" in content

    def test_substitutes_daemon_exec_placeholder(self, tmp_path: Path) -> None:
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/opt/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()
        content = (tmp_path / DAEMON_SERVICE).read_text()
        assert "ExecStart=/opt/venv/bin/github-monitor" in content
        assert "@@GITHUB_MONITOR_EXEC@@" not in content

    def test_substitutes_indicator_exec_placeholder(self, tmp_path: Path) -> None:
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch(
                "github_monitor.cli._systemd._resolve_exec",
                side_effect=lambda name: f"/opt/venv/bin/{name}",
            ),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files(include_indicator=True)
        content = (tmp_path / INDICATOR_SERVICE).read_text()
        assert "ExecStart=/opt/venv/bin/github-monitor-indicator" in content
        assert "@@GITHUB_MONITOR_INDICATOR_EXEC@@" not in content

    def test_disables_and_reenables_previously_enabled_daemon(self, tmp_path: Path) -> None:
        """When reinstalling an already-enabled daemon, disable before overwrite and re-enable after."""
        (tmp_path / DAEMON_SERVICE).write_text("old content")
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=True),
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)) as mock_ctl,
            patch("github_monitor.cli._systemd.enable") as mock_enable,
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()
        mock_ctl.assert_called_once_with("disable", DAEMON_SERVICE)
        mock_enable.assert_called_once_with(DAEMON_SERVICE)

    def test_disables_and_reenables_both_when_both_enabled(self, tmp_path: Path) -> None:
        """Both daemon and indicator are re-enabled when both were previously enabled."""
        (tmp_path / DAEMON_SERVICE).write_text("old content")
        (tmp_path / INDICATOR_SERVICE).write_text("old content")
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch(
                "github_monitor.cli._systemd._resolve_exec",
                side_effect=lambda name: f"/venv/bin/{name}",
            ),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=True),
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)) as mock_ctl,
            patch("github_monitor.cli._systemd.enable") as mock_enable,
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files(include_indicator=True)
        # Both should have been disabled before overwrite
        assert mock_ctl.call_count == 2
        mock_ctl.assert_any_call("disable", DAEMON_SERVICE)
        mock_ctl.assert_any_call("disable", INDICATOR_SERVICE)
        # Both should have been re-enabled after reload
        assert mock_enable.call_count == 2
        mock_enable.assert_any_call(DAEMON_SERVICE)
        mock_enable.assert_any_call(INDICATOR_SERVICE)

    def test_skips_disable_for_fresh_install(self, tmp_path: Path) -> None:
        """No disable call when service files don't exist yet (fresh install)."""
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled") as mock_is_enabled,
            patch("github_monitor.cli._systemd._run_systemctl") as mock_ctl,
            patch("github_monitor.cli._systemd.enable") as mock_enable,
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()
        # File doesn't exist, so is_enabled should not be called
        mock_is_enabled.assert_not_called()
        # No disable or enable calls
        mock_ctl.assert_not_called()
        mock_enable.assert_not_called()

    def test_skips_reenable_for_disabled_service(self, tmp_path: Path) -> None:
        """When reinstalling a service that exists but is not enabled, skip disable+enable."""
        (tmp_path / DAEMON_SERVICE).write_text("old content")
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd._resolve_exec", return_value="/venv/bin/github-monitor"),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.is_enabled", return_value=False),
            patch("github_monitor.cli._systemd._run_systemctl") as mock_ctl,
            patch("github_monitor.cli._systemd.enable") as mock_enable,
            patch("github_monitor.cli._systemd.ok"),
        ):
            install_service_files()
        mock_ctl.assert_not_called()
        mock_enable.assert_not_called()


# ---------------------------------------------------------------------------
# remove_service_files
# ---------------------------------------------------------------------------


class TestRemoveServiceFiles:
    """Tests for remove_service_files()."""

    def test_removes_existing_files(self, tmp_path: Path) -> None:
        (tmp_path / DAEMON_SERVICE).write_text("x")
        (tmp_path / INDICATOR_SERVICE).write_text("x")
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.ok"),
        ):
            remove_service_files()
        assert not (tmp_path / DAEMON_SERVICE).exists()
        assert not (tmp_path / INDICATOR_SERVICE).exists()

    def test_handles_missing_files_gracefully(self, tmp_path: Path) -> None:
        """No error when files don't exist."""
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            remove_service_files()  # should not raise
        mock_ok.assert_not_called()

    def test_removes_only_existing_file(self, tmp_path: Path) -> None:
        """Only daemon service exists; indicator should be skipped."""
        (tmp_path / DAEMON_SERVICE).write_text("x")
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd.daemon_reload"),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            remove_service_files()
        assert not (tmp_path / DAEMON_SERVICE).exists()
        mock_ok.assert_called_once()
        assert DAEMON_SERVICE in mock_ok.call_args[0][0]

    def test_calls_daemon_reload_after_removal(self, tmp_path: Path) -> None:
        with (
            patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path),
            patch("github_monitor.cli._systemd.daemon_reload") as mock_reload,
            patch("github_monitor.cli._systemd.ok"),
        ):
            remove_service_files()
        mock_reload.assert_called_once()


# ---------------------------------------------------------------------------
# daemon_reload
# ---------------------------------------------------------------------------


class TestDaemonReload:
    """Tests for daemon_reload()."""

    def test_calls_systemctl_daemon_reload(self) -> None:
        with patch("github_monitor.cli._systemd._run_systemctl") as mock_run:
            daemon_reload()
        mock_run.assert_called_once_with("daemon-reload")


# ---------------------------------------------------------------------------
# is_active / is_enabled — boolean queries
# ---------------------------------------------------------------------------


class TestIsActive:
    """Tests for is_active()."""

    def test_returns_true_when_active(self) -> None:
        with patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)):
            assert is_active("github-monitor.service") is True

    def test_returns_false_when_inactive(self) -> None:
        with patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(3)):
            assert is_active("github-monitor.service") is False

    def test_passes_correct_args(self) -> None:
        with patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)) as mock_run:
            is_active("github-monitor.service")
        mock_run.assert_called_once_with("is-active", "--quiet", "github-monitor.service")


class TestIsEnabled:
    """Tests for is_enabled()."""

    def test_returns_true_when_enabled(self) -> None:
        with patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)):
            assert is_enabled("github-monitor.service") is True

    def test_returns_false_when_disabled(self) -> None:
        with patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(1)):
            assert is_enabled("github-monitor.service") is False

    def test_passes_correct_args(self) -> None:
        with patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)) as mock_run:
            is_enabled("github-monitor.service")
        mock_run.assert_called_once_with("is-enabled", "--quiet", "github-monitor.service")


# ---------------------------------------------------------------------------
# start / stop / restart / enable / disable — action commands
# ---------------------------------------------------------------------------


class TestStart:
    """Tests for start()."""

    def test_success_prints_ok(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            start("github-monitor.service")
        mock_ok.assert_called_once()
        assert "Started" in mock_ok.call_args[0][0]

    def test_failure_prints_warn(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(1)),
            patch("github_monitor.cli._systemd.warn") as mock_warn,
        ):
            start("github-monitor.service")
        mock_warn.assert_called_once()
        assert "Failed" in mock_warn.call_args[0][0]

    def test_passes_correct_args(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)) as mock_run,
            patch("github_monitor.cli._systemd.ok"),
        ):
            start("github-monitor.service")
        mock_run.assert_called_once_with("start", "github-monitor.service")


class TestStop:
    """Tests for stop()."""

    def test_success_prints_ok(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            stop("github-monitor.service")
        mock_ok.assert_called_once()
        assert "Stopped" in mock_ok.call_args[0][0]

    def test_failure_prints_warn(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(1)),
            patch("github_monitor.cli._systemd.warn") as mock_warn,
        ):
            stop("github-monitor.service")
        mock_warn.assert_called_once()


class TestRestart:
    """Tests for restart()."""

    def test_success_prints_ok(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            restart("github-monitor.service")
        mock_ok.assert_called_once()
        assert "Restarted" in mock_ok.call_args[0][0]

    def test_failure_prints_warn(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(1)),
            patch("github_monitor.cli._systemd.warn") as mock_warn,
        ):
            restart("github-monitor.service")
        mock_warn.assert_called_once()


class TestEnable:
    """Tests for enable()."""

    def test_success_prints_ok(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            enable("github-monitor.service")
        mock_ok.assert_called_once()
        assert "Enabled" in mock_ok.call_args[0][0]

    def test_failure_prints_warn(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(1)),
            patch("github_monitor.cli._systemd.warn") as mock_warn,
        ):
            enable("github-monitor.service")
        mock_warn.assert_called_once()


class TestDisable:
    """Tests for disable()."""

    def test_success_prints_ok(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(0)),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            disable("github-monitor.service")
        mock_ok.assert_called_once()
        assert "Disabled" in mock_ok.call_args[0][0]

    def test_failure_prints_warn(self) -> None:
        with (
            patch("github_monitor.cli._systemd._run_systemctl", return_value=_make_completed_process(1)),
            patch("github_monitor.cli._systemd.warn") as mock_warn,
        ):
            disable("github-monitor.service")
        mock_warn.assert_called_once()


# ---------------------------------------------------------------------------
# print_status — prints directly to terminal
# ---------------------------------------------------------------------------


class TestPrintStatus:
    """Tests for print_status()."""

    def test_calls_systemctl_status(self) -> None:
        with patch("github_monitor.cli._systemd.subprocess.run") as mock_run:
            print_status("github-monitor.service")
        mock_run.assert_called_once_with(
            ["systemctl", "--user", "status", "github-monitor.service", "--no-pager"],
            check=False,
        )


# ---------------------------------------------------------------------------
# service_file_installed — path existence check
# ---------------------------------------------------------------------------


class TestServiceFileInstalled:
    """Tests for service_file_installed()."""

    def test_returns_true_when_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / DAEMON_SERVICE).write_text("x")
        with patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path):
            assert service_file_installed(DAEMON_SERVICE) is True

    def test_returns_false_when_file_missing(self, tmp_path: Path) -> None:
        with patch("github_monitor.cli._systemd.SERVICE_DIR", tmp_path):
            assert service_file_installed(DAEMON_SERVICE) is False


# ---------------------------------------------------------------------------
# remove_legacy_autostart — removes XDG autostart desktop file
# ---------------------------------------------------------------------------


class TestRemoveLegacyAutostart:
    """Tests for remove_legacy_autostart()."""

    def test_removes_existing_desktop_file(self, tmp_path: Path) -> None:
        desktop_file = tmp_path / "github-monitor-indicator.desktop"
        desktop_file.write_text("[Desktop Entry]\nExec=github-monitor-indicator")
        with (
            patch("github_monitor.cli._systemd._LEGACY_AUTOSTART", desktop_file),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            remove_legacy_autostart()
        assert not desktop_file.exists()
        mock_ok.assert_called_once()
        assert "legacy" in mock_ok.call_args[0][0].lower()

    def test_does_nothing_when_file_missing(self, tmp_path: Path) -> None:
        desktop_file = tmp_path / "github-monitor-indicator.desktop"
        with (
            patch("github_monitor.cli._systemd._LEGACY_AUTOSTART", desktop_file),
            patch("github_monitor.cli._systemd.ok") as mock_ok,
        ):
            remove_legacy_autostart()  # should not raise
        mock_ok.assert_not_called()

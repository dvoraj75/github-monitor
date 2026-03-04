"""Tests for github_monitor.cli.setup."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from github_monitor.cli.setup import (
    _config_wizard,
    _format_repos_toml,
    _print_summary,
    _start_or_restart,
    _write_config,
    run_setup,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


# ---------------------------------------------------------------------------
# _format_repos_toml
# ---------------------------------------------------------------------------


class TestFormatReposToml:
    """Verify TOML array formatting for repo lists."""

    def test_empty_list(self) -> None:
        assert _format_repos_toml([]) == "[]"

    def test_single_repo(self) -> None:
        assert _format_repos_toml(["owner/repo"]) == '["owner/repo"]'

    def test_multiple_repos(self) -> None:
        result = _format_repos_toml(["alice/foo", "bob/bar"])
        assert result == '["alice/foo", "bob/bar"]'

    def test_three_repos(self) -> None:
        result = _format_repos_toml(["a/b", "c/d", "e/f"])
        assert result == '["a/b", "c/d", "e/f"]'


# ---------------------------------------------------------------------------
# _write_config
# ---------------------------------------------------------------------------


class TestWriteConfig:
    """Verify config file creation, content, and permissions."""

    def test_creates_directory_and_file(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_path = config_dir / "config.toml"

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
        ):
            _write_config("ghp_abc123", "testuser", 300, [])

        assert config_dir.is_dir()
        assert config_path.exists()

    def test_file_content_matches_template(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_path = config_dir / "config.toml"

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
        ):
            _write_config("ghp_token", "alice", 600, ["org/repo1", "org/repo2"])

        content = config_path.read_text(encoding="utf-8")
        assert 'github_token = "ghp_token"' in content
        assert 'github_username = "alice"' in content
        assert "poll_interval = 600" in content
        assert 'repos = ["org/repo1", "org/repo2"]' in content

    def test_file_content_empty_repos(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_path = config_dir / "config.toml"

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
        ):
            _write_config("ghp_token", "bob", 300, [])

        content = config_path.read_text(encoding="utf-8")
        assert "repos = []" in content

    def test_file_permissions_600(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_path = config_dir / "config.toml"

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
        ):
            _write_config("ghp_token", "user", 300, [])

        mode = config_path.stat().st_mode
        assert mode & 0o777 == stat.S_IRUSR | stat.S_IWUSR  # 0o600

    def test_existing_directory_no_error(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_dir.mkdir()
        config_path = config_dir / "config.toml"

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
        ):
            _write_config("ghp_token", "user", 300, [])

        assert config_path.exists()


# ---------------------------------------------------------------------------
# _config_wizard
# ---------------------------------------------------------------------------


class TestConfigWizard:
    """Verify the interactive config wizard flow."""

    def test_prompts_and_writes_config(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_path = config_dir / "config.toml"

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
            patch("github_monitor.cli.setup.ask_string", side_effect=["ghp_abc", "myuser"]),
            patch("github_monitor.cli.setup.ask_int", return_value=120),
            patch("github_monitor.cli.setup.ask_list", return_value=["org/repo"]),
        ):
            _config_wizard()

        content = config_path.read_text(encoding="utf-8")
        assert 'github_token = "ghp_abc"' in content
        assert 'github_username = "myuser"' in content
        assert "poll_interval = 120" in content
        assert 'repos = ["org/repo"]' in content

    def test_existing_config_decline_overwrite(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text("old content", encoding="utf-8")

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
            patch("github_monitor.cli.setup.ask_yes_no", return_value=False),
            patch("github_monitor.cli.setup.ask_string") as mock_ask_string,
        ):
            _config_wizard()

        # Should not have prompted for token/username
        mock_ask_string.assert_not_called()
        # Original content preserved
        assert config_path.read_text(encoding="utf-8") == "old content"

    def test_existing_config_accept_overwrite(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "github-monitor"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text("old content", encoding="utf-8")

        with (
            patch("github_monitor.cli.setup.CONFIG_DIR", config_dir),
            patch("github_monitor.cli.setup.CONFIG_PATH", config_path),
            patch("github_monitor.cli.setup.ask_yes_no", return_value=True),
            patch("github_monitor.cli.setup.ask_string", side_effect=["ghp_new", "newuser"]),
            patch("github_monitor.cli.setup.ask_int", return_value=300),
            patch("github_monitor.cli.setup.ask_list", return_value=[]),
        ):
            _config_wizard()

        content = config_path.read_text(encoding="utf-8")
        assert 'github_token = "ghp_new"' in content
        assert "old content" not in content


# ---------------------------------------------------------------------------
# _start_or_restart
# ---------------------------------------------------------------------------


class TestStartOrRestart:
    """Verify service start vs restart logic."""

    @patch("github_monitor.cli.setup._systemd")
    def test_starts_when_inactive(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = False
        _start_or_restart("github-monitor.service")
        mock_systemd.start.assert_called_once_with("github-monitor.service")
        mock_systemd.restart.assert_not_called()

    @patch("github_monitor.cli.setup._systemd")
    def test_restarts_when_active(self, mock_systemd: MagicMock) -> None:
        mock_systemd.is_active.return_value = True
        _start_or_restart("github-monitor.service")
        mock_systemd.restart.assert_called_once_with("github-monitor.service")
        mock_systemd.start.assert_not_called()


# ---------------------------------------------------------------------------
# _print_summary
# ---------------------------------------------------------------------------


class TestPrintSummary:
    """Verify summary output content."""

    def test_includes_config_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_summary(has_gtk=False, has_systemctl=True)
        output = capsys.readouterr().out
        assert "Setup complete!" in output
        assert "config.toml" in output

    def test_includes_systemctl_commands(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_summary(has_gtk=False, has_systemctl=True)
        output = capsys.readouterr().out
        assert "systemctl --user status github-monitor" in output
        assert "journalctl --user -u github-monitor" in output

    def test_no_systemctl_commands_when_unavailable(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_summary(has_gtk=False, has_systemctl=False)
        output = capsys.readouterr().out
        assert "Setup complete!" in output
        assert "systemctl" not in output

    def test_includes_indicator_commands_when_gtk(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_summary(has_gtk=True, has_systemctl=True)
        output = capsys.readouterr().out
        assert "github-monitor-indicator" in output

    def test_no_indicator_commands_without_gtk(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_summary(has_gtk=False, has_systemctl=True)
        output = capsys.readouterr().out
        assert "github-monitor-indicator" not in output


# ---------------------------------------------------------------------------
# run_setup -- full flow
# ---------------------------------------------------------------------------


class TestRunSetupFull:
    """Verify the full setup flow (no flags)."""

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_full_flow_calls_all_steps(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False
        mock_checks.check_systemctl.return_value = True
        mock_systemd.is_active.return_value = False

        run_setup()

        # All checks called
        mock_checks.check_notify_send.assert_called_once()
        mock_checks.check_dbus_session.assert_called_once()
        mock_checks.check_gtk_indicator.assert_called_once()
        mock_checks.check_systemctl.assert_called_once()

        # Config wizard called
        mock_wizard.assert_called_once()

        # Services installed, enabled, started
        mock_systemd.install_service_files.assert_called_once_with(include_indicator=False)
        mock_systemd.enable.assert_called_once_with(mock_systemd.DAEMON_SERVICE)
        mock_systemd.start.assert_called_once_with(mock_systemd.DAEMON_SERVICE)

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_full_flow_with_gtk(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = True
        mock_checks.check_systemctl.return_value = True
        mock_systemd.is_active.return_value = False

        run_setup()

        mock_systemd.install_service_files.assert_called_once_with(include_indicator=True)
        # Both daemon and indicator enabled+started
        assert mock_systemd.enable.call_count == 2
        assert mock_systemd.start.call_count == 2
        mock_systemd.enable.assert_any_call(mock_systemd.DAEMON_SERVICE)
        mock_systemd.enable.assert_any_call(mock_systemd.INDICATOR_SERVICE)

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_restart_when_already_active(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False
        mock_checks.check_systemctl.return_value = True
        mock_systemd.is_active.return_value = True

        run_setup()

        mock_systemd.restart.assert_called_once_with(mock_systemd.DAEMON_SERVICE)
        mock_systemd.start.assert_not_called()


# ---------------------------------------------------------------------------
# run_setup -- config-only
# ---------------------------------------------------------------------------


class TestRunSetupConfigOnly:
    """Verify --config-only mode."""

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_config_only_skips_systemctl_check(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False

        run_setup(config_only=True)

        mock_checks.check_systemctl.assert_not_called()

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_config_only_skips_service_operations(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False

        run_setup(config_only=True)

        mock_systemd.install_service_files.assert_not_called()
        mock_systemd.enable.assert_not_called()
        mock_systemd.start.assert_not_called()
        mock_systemd.restart.assert_not_called()

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_config_only_runs_wizard(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False

        run_setup(config_only=True)

        mock_wizard.assert_called_once()


# ---------------------------------------------------------------------------
# run_setup -- service-only
# ---------------------------------------------------------------------------


class TestRunSetupServiceOnly:
    """Verify --service-only mode."""

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_service_only_skips_wizard(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False
        mock_checks.check_systemctl.return_value = True
        mock_systemd.is_active.return_value = False

        run_setup(service_only=True)

        mock_wizard.assert_not_called()

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_service_only_installs_and_starts(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False
        mock_checks.check_systemctl.return_value = True
        mock_systemd.is_active.return_value = False

        run_setup(service_only=True)

        mock_systemd.install_service_files.assert_called_once_with(include_indicator=False)
        mock_systemd.enable.assert_called_once_with(mock_systemd.DAEMON_SERVICE)
        mock_systemd.start.assert_called_once_with(mock_systemd.DAEMON_SERVICE)


# ---------------------------------------------------------------------------
# run_setup -- no systemctl
# ---------------------------------------------------------------------------


class TestRunSetupNoSystemctl:
    """Verify graceful degradation when systemctl is missing."""

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_no_systemctl_skips_service_steps(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False
        mock_checks.check_systemctl.return_value = False

        run_setup()

        # Config wizard still runs
        mock_wizard.assert_called_once()

        # But no service operations
        mock_systemd.install_service_files.assert_not_called()
        mock_systemd.enable.assert_not_called()
        mock_systemd.start.assert_not_called()

    @patch("github_monitor.cli.setup._systemd")
    @patch("github_monitor.cli.setup._checks")
    @patch("github_monitor.cli.setup._config_wizard")
    def test_no_systemctl_summary_omits_commands(
        self,
        mock_wizard: MagicMock,
        mock_checks: MagicMock,
        mock_systemd: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_checks.check_notify_send.return_value = True
        mock_checks.check_dbus_session.return_value = True
        mock_checks.check_gtk_indicator.return_value = False
        mock_checks.check_systemctl.return_value = False

        run_setup()

        output = capsys.readouterr().out
        assert "Setup complete!" in output
        # Should not include systemctl commands since systemctl is unavailable
        assert "systemctl --user status" not in output

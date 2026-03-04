"""Tests for github_monitor.cli (build_parser + run_cli)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from github_monitor.cli import build_parser, run_cli

# ---------------------------------------------------------------------------
# build_parser — argparse structure
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Verify the argparse parser structure."""

    def test_returns_argument_parser(self) -> None:
        parser = build_parser()
        assert parser.prog == "github-monitor"

    def test_setup_subcommand_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["setup"])
        assert args.command == "setup"

    def test_setup_config_only_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["setup", "--config-only"])
        assert args.config_only is True
        assert args.service_only is False

    def test_setup_service_only_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["setup", "--service-only"])
        assert args.service_only is True
        assert args.config_only is False

    def test_setup_flags_mutually_exclusive(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["setup", "--config-only", "--service-only"])

    def test_setup_no_flags_default(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["setup"])
        assert args.config_only is False
        assert args.service_only is False

    def test_service_subcommand_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["service", "start"])
        assert args.command == "service"
        assert args.action == "start"

    def test_service_all_actions_valid(self) -> None:
        parser = build_parser()
        for action in ("install", "start", "stop", "restart", "status", "enable", "disable"):
            args = parser.parse_args(["service", action])
            assert args.action == action

    def test_service_invalid_action_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["service", "bogus"])

    def test_service_missing_action_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["service"])

    def test_uninstall_subcommand_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["uninstall"])
        assert args.command == "uninstall"

    def test_no_command_sets_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None


# ---------------------------------------------------------------------------
# run_cli — dispatch logic
# ---------------------------------------------------------------------------


class TestRunCli:
    """Verify run_cli dispatches to the correct subcommand handler."""

    @patch("github_monitor.cli.setup.run_setup")
    def test_dispatches_setup(self, mock_run_setup: MagicMock) -> None:
        run_cli(["setup"])
        mock_run_setup.assert_called_once_with(config_only=False, service_only=False)

    @patch("github_monitor.cli.setup.run_setup")
    def test_dispatches_setup_config_only(self, mock_run_setup: MagicMock) -> None:
        run_cli(["setup", "--config-only"])
        mock_run_setup.assert_called_once_with(config_only=True, service_only=False)

    @patch("github_monitor.cli.setup.run_setup")
    def test_dispatches_setup_service_only(self, mock_run_setup: MagicMock) -> None:
        run_cli(["setup", "--service-only"])
        mock_run_setup.assert_called_once_with(config_only=False, service_only=True)

    @patch("github_monitor.cli.service.run_service")
    def test_dispatches_service_start(self, mock_run_service: MagicMock) -> None:
        run_cli(["service", "start"])
        mock_run_service.assert_called_once_with(action="start")

    @patch("github_monitor.cli.service.run_service")
    def test_dispatches_service_stop(self, mock_run_service: MagicMock) -> None:
        run_cli(["service", "stop"])
        mock_run_service.assert_called_once_with(action="stop")

    @patch("github_monitor.cli.service.run_service")
    def test_dispatches_service_status(self, mock_run_service: MagicMock) -> None:
        run_cli(["service", "status"])
        mock_run_service.assert_called_once_with(action="status")

    @patch("github_monitor.cli.service.run_service")
    def test_dispatches_service_install(self, mock_run_service: MagicMock) -> None:
        run_cli(["service", "install"])
        mock_run_service.assert_called_once_with(action="install")

    @patch("github_monitor.cli.service.run_service")
    def test_dispatches_service_restart(self, mock_run_service: MagicMock) -> None:
        run_cli(["service", "restart"])
        mock_run_service.assert_called_once_with(action="restart")

    @patch("github_monitor.cli.service.run_service")
    def test_dispatches_service_enable(self, mock_run_service: MagicMock) -> None:
        run_cli(["service", "enable"])
        mock_run_service.assert_called_once_with(action="enable")

    @patch("github_monitor.cli.service.run_service")
    def test_dispatches_service_disable(self, mock_run_service: MagicMock) -> None:
        run_cli(["service", "disable"])
        mock_run_service.assert_called_once_with(action="disable")

    @patch("github_monitor.cli.uninstall.run_uninstall")
    def test_dispatches_uninstall(self, mock_run_uninstall: MagicMock) -> None:
        run_cli(["uninstall"])
        mock_run_uninstall.assert_called_once_with()

    def test_no_command_prints_help_and_exits(self) -> None:
        with pytest.raises(SystemExit, match="1"):
            run_cli([])

    def test_explicit_argv_used(self) -> None:
        """Verify run_cli uses the provided argv, not sys.argv."""
        with pytest.raises(SystemExit, match="1"):
            run_cli([])

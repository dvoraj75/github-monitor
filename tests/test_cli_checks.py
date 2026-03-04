"""Tests for github_monitor.cli._checks."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from github_monitor.cli._checks import check_dbus_session, check_gtk_indicator, check_notify_send, check_systemctl

if TYPE_CHECKING:
    import pytest


# ---------------------------------------------------------------------------
# check_notify_send
# ---------------------------------------------------------------------------


class TestCheckNotifySend:
    """Tests for check_notify_send()."""

    def test_found_returns_true(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value="/usr/bin/notify-send"),
            patch("github_monitor.cli._checks.ok"),
        ):
            assert check_notify_send() is True

    def test_found_prints_ok(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value="/usr/bin/notify-send"),
            patch("github_monitor.cli._checks.ok") as mock_ok,
        ):
            check_notify_send()
        mock_ok.assert_called_once()
        assert "notify-send" in mock_ok.call_args[0][0]

    def test_missing_returns_false(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value=None),
            patch("github_monitor.cli._checks.warn"),
            patch("github_monitor.cli._checks.info"),
        ):
            assert check_notify_send() is False

    def test_missing_prints_warning_and_install_hint(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value=None),
            patch("github_monitor.cli._checks.warn") as mock_warn,
            patch("github_monitor.cli._checks.info") as mock_info,
        ):
            check_notify_send()
        mock_warn.assert_called_once()
        mock_info.assert_called_once()
        assert "libnotify" in mock_info.call_args[0][0]


# ---------------------------------------------------------------------------
# check_dbus_session
# ---------------------------------------------------------------------------


class TestCheckDbusSession:
    """Tests for check_dbus_session()."""

    def test_env_set_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
        with patch("github_monitor.cli._checks.ok"):
            assert check_dbus_session() is True

    def test_env_set_prints_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
        with patch("github_monitor.cli._checks.ok") as mock_ok:
            check_dbus_session()
        mock_ok.assert_called_once()

    def test_env_missing_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
        with (
            patch("github_monitor.cli._checks.warn"),
            patch("github_monitor.cli._checks.info"),
        ):
            assert check_dbus_session() is False

    def test_env_missing_prints_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
        with (
            patch("github_monitor.cli._checks.warn") as mock_warn,
            patch("github_monitor.cli._checks.info"),
        ):
            check_dbus_session()
        mock_warn.assert_called_once()
        assert "DBUS_SESSION_BUS_ADDRESS" in mock_warn.call_args[0][0]

    def test_env_empty_string_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "")
        with (
            patch("github_monitor.cli._checks.warn"),
            patch("github_monitor.cli._checks.info"),
        ):
            assert check_dbus_session() is False


# ---------------------------------------------------------------------------
# check_gtk_indicator
# ---------------------------------------------------------------------------


class TestCheckGtkIndicator:
    """Tests for check_gtk_indicator()."""

    def test_importable_returns_true(self) -> None:
        mock_gi = MagicMock()
        with (
            patch.dict("sys.modules", {"gi": mock_gi}),
            patch("github_monitor.cli._checks.ok"),
        ):
            assert check_gtk_indicator() is True

    def test_importable_prints_ok(self) -> None:
        mock_gi = MagicMock()
        with (
            patch.dict("sys.modules", {"gi": mock_gi}),
            patch("github_monitor.cli._checks.ok") as mock_ok,
        ):
            check_gtk_indicator()
        mock_ok.assert_called_once()
        assert "GTK3" in mock_ok.call_args[0][0]

    def test_import_error_returns_false(self) -> None:
        with (
            patch.dict("sys.modules", {"gi": None}),
            patch("github_monitor.cli._checks.warn"),
            patch("github_monitor.cli._checks.info"),
        ):
            assert check_gtk_indicator() is False

    def test_import_error_prints_warning_and_install_hint(self) -> None:
        with (
            patch.dict("sys.modules", {"gi": None}),
            patch("github_monitor.cli._checks.warn") as mock_warn,
            patch("github_monitor.cli._checks.info") as mock_info,
        ):
            check_gtk_indicator()
        mock_warn.assert_called_once()
        assert mock_info.call_count == 2

    def test_value_error_from_require_version_returns_false(self) -> None:
        mock_gi = MagicMock()
        mock_gi.require_version.side_effect = ValueError("Namespace not available")
        with (
            patch.dict("sys.modules", {"gi": mock_gi}),
            patch("github_monitor.cli._checks.warn"),
            patch("github_monitor.cli._checks.info"),
        ):
            assert check_gtk_indicator() is False


# ---------------------------------------------------------------------------
# check_systemctl
# ---------------------------------------------------------------------------


class TestCheckSystemctl:
    """Tests for check_systemctl()."""

    def test_found_returns_true(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value="/usr/bin/systemctl"),
            patch("github_monitor.cli._checks.ok"),
        ):
            assert check_systemctl() is True

    def test_found_prints_ok(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value="/usr/bin/systemctl"),
            patch("github_monitor.cli._checks.ok") as mock_ok,
        ):
            check_systemctl()
        mock_ok.assert_called_once()
        assert "systemctl" in mock_ok.call_args[0][0]

    def test_missing_returns_false(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value=None),
            patch("github_monitor.cli._checks.warn"),
        ):
            assert check_systemctl() is False

    def test_missing_prints_warning(self) -> None:
        with (
            patch("github_monitor.cli._checks.shutil.which", return_value=None),
            patch("github_monitor.cli._checks.warn") as mock_warn,
        ):
            check_systemctl()
        mock_warn.assert_called_once()
        assert "systemctl" in mock_warn.call_args[0][0]

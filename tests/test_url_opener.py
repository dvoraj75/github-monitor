"""Tests for github_monitor.url_opener — browser opening via XDG Desktop Portal / xdg-open."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from dbus_next.constants import MessageType
from dbus_next.errors import DBusError

from github_monitor.url_opener import _open_url_portal, _open_url_xdg, open_url
from tests.conftest import _mock_process

if TYPE_CHECKING:
    from dbus_next.message import Message

# ---------------------------------------------------------------------------
# Tests: _open_url — browser opening via XDG Desktop Portal / xdg-open
# ---------------------------------------------------------------------------


class TestOpenUrlPortal:
    """_open_url_portal opens URLs via the XDG Desktop Portal D-Bus API."""

    def _mock_bus(self, *, reply_type: MessageType = MessageType.METHOD_RETURN) -> AsyncMock:
        """Build a mock MessageBus whose ``call()`` returns a fake reply."""
        reply = MagicMock()
        reply.message_type = reply_type
        reply.error_name = "org.freedesktop.portal.Error.Failed" if reply_type == MessageType.ERROR else None
        reply.body = ["failed"] if reply_type == MessageType.ERROR else []
        bus = AsyncMock()
        bus.connect.return_value = bus
        bus.call.return_value = reply
        bus.disconnect = MagicMock()
        return bus

    async def test_portal_success(self) -> None:
        """Portal call succeeds — returns True, sends correct Message."""
        bus = self._mock_bus()

        with patch("github_monitor.url_opener.MessageBus", return_value=bus):
            result = await _open_url_portal("https://github.com/owner/repo/pull/1")

        assert result is True
        bus.call.assert_awaited_once()
        sent_msg: Message = bus.call.call_args[0][0]
        assert sent_msg.member == "OpenURI"
        assert sent_msg.body == ["", "https://github.com/owner/repo/pull/1", {}]
        bus.disconnect.assert_called_once()

    async def test_portal_dbus_error_returns_false(self) -> None:
        """bus.call raises DBusError — returns False for fallback."""
        bus = self._mock_bus()
        bus.call.side_effect = DBusError("org.freedesktop.DBus.Error.ServiceUnknown", "not found")

        with patch("github_monitor.url_opener.MessageBus", return_value=bus):
            result = await _open_url_portal("https://github.com/owner/repo/pull/1")

        assert result is False
        bus.disconnect.assert_called_once()

    async def test_portal_connect_oserror_returns_false(self) -> None:
        """Bus connection raises OSError — returns False for fallback."""
        bus = AsyncMock()
        bus.connect.side_effect = OSError("no session bus")

        with patch("github_monitor.url_opener.MessageBus", return_value=bus):
            result = await _open_url_portal("https://github.com/owner/repo/pull/1")

        assert result is False

    async def test_portal_error_reply_returns_false(self) -> None:
        """Portal returns an ERROR reply — returns False for fallback."""
        bus = self._mock_bus(reply_type=MessageType.ERROR)

        with patch("github_monitor.url_opener.MessageBus", return_value=bus):
            result = await _open_url_portal("https://github.com/owner/repo/pull/1")

        assert result is False
        bus.disconnect.assert_called_once()

    async def test_portal_no_reply_returns_false(self) -> None:
        """bus.call returns None — returns False for fallback."""
        bus = self._mock_bus()
        bus.call.return_value = None

        with patch("github_monitor.url_opener.MessageBus", return_value=bus):
            result = await _open_url_portal("https://github.com/owner/repo/pull/1")

        assert result is False
        bus.disconnect.assert_called_once()


class TestOpenUrlXdg:
    """_open_url_xdg opens URLs via the xdg-open subprocess."""

    async def test_successful_open(self) -> None:
        """xdg-open exits 0 — no warning logged."""
        proc = _mock_process(returncode=0)

        with (
            patch(
                "github_monitor.url_opener.asyncio.create_subprocess_exec",
                return_value=proc,
            ) as mock_exec,
            patch("github_monitor.url_opener.logger") as mock_logger,
        ):
            await _open_url_xdg("https://github.com/owner/repo/pull/1")

            mock_exec.assert_awaited_once_with(
                "xdg-open",
                "https://github.com/owner/repo/pull/1",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            mock_logger.warning.assert_not_called()

    async def test_logs_warning_on_nonzero_exit(self) -> None:
        """xdg-open exits non-zero — warning with stderr is logged."""
        proc = _mock_process(returncode=1, stderr=b"cannot find browser")

        with (
            patch(
                "github_monitor.url_opener.asyncio.create_subprocess_exec",
                return_value=proc,
            ),
            patch("github_monitor.url_opener.logger") as mock_logger,
        ):
            await _open_url_xdg("https://github.com/owner/repo/pull/1")

            mock_logger.warning.assert_called_once()
            args = mock_logger.warning.call_args[0]
            assert "xdg-open failed" in args[0]
            assert args[2] == "https://github.com/owner/repo/pull/1"
            assert args[3] == "cannot find browser"

    async def test_logs_warning_when_xdg_open_not_found(self) -> None:
        """xdg-open not installed — FileNotFoundError is caught and logged."""
        with (
            patch(
                "github_monitor.url_opener.asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError,
            ),
            patch("github_monitor.url_opener.logger") as mock_logger,
        ):
            await _open_url_xdg("https://github.com/owner/repo/pull/1")

            mock_logger.warning.assert_called_once()
            assert "xdg-open not found" in mock_logger.warning.call_args[0][0]

    async def test_oserror_does_not_propagate(self) -> None:
        """OSError during subprocess creation is caught, not propagated."""
        with patch(
            "github_monitor.url_opener.asyncio.create_subprocess_exec",
            side_effect=OSError("unexpected"),
        ):
            # Should not raise
            await _open_url_xdg("https://github.com/owner/repo/pull/1")


class TestOpenUrl:
    """_open_url tries the portal first, then falls back to xdg-open."""

    async def test_uses_portal_when_available(self) -> None:
        """Portal succeeds — xdg-open is not called."""
        with (
            patch(
                "github_monitor.url_opener._open_url_portal", new_callable=AsyncMock, return_value=True
            ) as mock_portal,
            patch("github_monitor.url_opener._open_url_xdg", new_callable=AsyncMock) as mock_xdg,
        ):
            await open_url("https://github.com/owner/repo/pull/1")

            mock_portal.assert_awaited_once_with("https://github.com/owner/repo/pull/1")
            mock_xdg.assert_not_awaited()

    async def test_falls_back_to_xdg_open(self) -> None:
        """Portal unavailable — falls back to xdg-open."""
        with (
            patch(
                "github_monitor.url_opener._open_url_portal", new_callable=AsyncMock, return_value=False
            ) as mock_portal,
            patch("github_monitor.url_opener._open_url_xdg", new_callable=AsyncMock) as mock_xdg,
        ):
            await open_url("https://github.com/owner/repo/pull/1")

            mock_portal.assert_awaited_once_with("https://github.com/owner/repo/pull/1")
            mock_xdg.assert_awaited_once_with("https://github.com/owner/repo/pull/1")

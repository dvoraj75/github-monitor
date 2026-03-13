"""Tests for forgewatch.indicator.client."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dbus_next.constants import MessageType
from dbus_next.errors import DBusError

from forgewatch.indicator.client import (
    BUS_NAME,
    INTERFACE_NAME,
    OBJECT_PATH,
    DaemonClient,
    _parse_pr,
    _parse_prs,
    _parse_status,
)
from forgewatch.indicator.models import DaemonStatus, PRInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
_NOW_ISO = "2026-03-01T12:00:00+00:00"


def _make_pr_dict(
    number: int = 42,
    *,
    repo: str = "owner/repo",
    title: str = "Fix login bug",
    review_requested: bool = True,
    assigned: bool = False,
    updated_at: str = _NOW_ISO,
) -> dict[str, Any]:
    """Build a PR dict matching the daemon's JSON serialisation format."""
    return {
        "url": f"https://github.com/{repo}/pull/{number}",
        "title": title,
        "repo": repo,
        "author": "octocat",
        "author_avatar_url": f"https://avatars.githubusercontent.com/u/{number}",
        "number": number,
        "updated_at": updated_at,
        "review_requested": review_requested,
        "assigned": assigned,
    }


def _make_status_dict(
    pr_count: int = 5,
    last_updated: str | None = _NOW_ISO,
) -> dict[str, Any]:
    """Build a status dict matching the daemon's JSON serialisation format."""
    return {
        "pr_count": pr_count,
        "last_updated": last_updated,
    }


def _make_prs_json(*dicts: dict[str, Any]) -> str:
    """Serialise PR dicts to a JSON string."""
    return json.dumps(list(dicts))


def _make_status_json(**kwargs: Any) -> str:
    """Serialise a status dict to a JSON string."""
    return json.dumps(_make_status_dict(**kwargs))


def _make_mock_bus() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Create mocked MessageBus, proxy, and interface.

    Returns (bus, proxy, interface) with sensible defaults wired up.
    The bus is a MagicMock with only ``introspect`` set up as async,
    since ``get_proxy_object`` and ``get_interface`` are synchronous in
    dbus-next.
    """
    interface = MagicMock()
    proxy = MagicMock()
    proxy.get_interface.return_value = interface

    bus = MagicMock()
    bus.introspect = AsyncMock(return_value=MagicMock())
    bus.get_proxy_object.return_value = proxy

    return bus, proxy, interface


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_bus_name(self) -> None:
        assert BUS_NAME == "org.forgewatch.Daemon"

    def test_object_path(self) -> None:
        assert OBJECT_PATH == "/org/forgewatch/Daemon"

    def test_interface_name(self) -> None:
        assert INTERFACE_NAME == "org.forgewatch.Daemon"


# ---------------------------------------------------------------------------
# Parsing — _parse_pr
# ---------------------------------------------------------------------------


class TestParsePr:
    def test_all_fields_parsed(self) -> None:
        data = _make_pr_dict(number=42, title="Fix login bug", repo="owner/repo")
        result = _parse_pr(data)

        assert isinstance(result, PRInfo)
        assert result.url == "https://github.com/owner/repo/pull/42"
        assert result.title == "Fix login bug"
        assert result.repo == "owner/repo"
        assert result.author == "octocat"
        assert result.author_avatar_url == "https://avatars.githubusercontent.com/u/42"
        assert result.number == 42
        assert result.updated_at == _NOW
        assert result.review_requested is True
        assert result.assigned is False

    def test_updated_at_parsed_as_datetime(self) -> None:
        data = _make_pr_dict(updated_at="2025-06-15T10:30:00+00:00")
        result = _parse_pr(data)

        assert result.updated_at == datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)

    def test_both_flags_true(self) -> None:
        data = _make_pr_dict(review_requested=True, assigned=True)
        result = _parse_pr(data)

        assert result.review_requested is True
        assert result.assigned is True

    def test_missing_key_raises(self) -> None:
        data: dict[str, object] = {"url": "https://example.com"}
        with pytest.raises(KeyError):
            _parse_pr(data)


# ---------------------------------------------------------------------------
# Parsing — _parse_prs
# ---------------------------------------------------------------------------


class TestParsePrs:
    def test_empty_array(self) -> None:
        result = _parse_prs("[]")
        assert result == []

    def test_single_pr(self) -> None:
        json_str = _make_prs_json(_make_pr_dict(number=1))
        result = _parse_prs(json_str)

        assert len(result) == 1
        assert result[0].number == 1

    def test_multiple_prs(self) -> None:
        json_str = _make_prs_json(
            _make_pr_dict(number=1),
            _make_pr_dict(number=2),
            _make_pr_dict(number=3),
        )
        result = _parse_prs(json_str)

        assert len(result) == 3
        assert [pr.number for pr in result] == [1, 2, 3]

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_prs("not json")


# ---------------------------------------------------------------------------
# Parsing — _parse_status
# ---------------------------------------------------------------------------


class TestParseStatus:
    def test_with_last_updated(self) -> None:
        json_str = _make_status_json(pr_count=5, last_updated=_NOW_ISO)
        result = _parse_status(json_str)

        assert isinstance(result, DaemonStatus)
        assert result.pr_count == 5
        assert result.last_updated == _NOW

    def test_null_last_updated(self) -> None:
        json_str = _make_status_json(pr_count=0, last_updated=None)
        result = _parse_status(json_str)

        assert result.pr_count == 0
        assert result.last_updated is None

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_status("{bad")


# ---------------------------------------------------------------------------
# DaemonClient — connect
# ---------------------------------------------------------------------------


class TestConnect:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_connect_success(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_prs = MagicMock()
        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=on_prs, on_connection_changed=on_conn)

        await client.connect()

        assert client.connected is True
        on_conn.assert_called_once_with(True)  # noqa: FBT003
        # Signal subscription was set up
        interface.on_pull_requests_changed.assert_called_once()
        # NameOwnerChanged watcher was registered
        bus.add_message_handler.assert_called_once()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_connect_failure_schedules_reconnect(self, mock_bus_class: MagicMock) -> None:
        mock_bus_class.return_value.connect = AsyncMock(side_effect=OSError("no bus"))

        on_prs = MagicMock()
        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=on_prs, on_connection_changed=on_conn)

        await client.connect()

        assert client.connected is False
        # on_connection_changed is NOT called when we were never connected
        on_conn.assert_not_called()
        # Reconnect is scheduled
        assert client._reconnect_handle is not None
        # Clean up the scheduled reconnect
        client._cancel_reconnect()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_connect_dbus_error_schedules_reconnect(self, mock_bus_class: MagicMock) -> None:
        mock_bus_class.return_value.connect = AsyncMock(
            side_effect=DBusError("org.freedesktop.DBus.Error.ServiceUnknown", "not found"),
        )

        on_prs = MagicMock()
        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=on_prs, on_connection_changed=on_conn)

        await client.connect()

        assert client.connected is False
        assert client._reconnect_handle is not None
        client._cancel_reconnect()


# ---------------------------------------------------------------------------
# DaemonClient — disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_disconnect_cleans_up(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, _interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()
        assert client.connected is True

        await client.disconnect()

        assert client.connected is False
        bus.disconnect.assert_called_once()

    async def test_disconnect_when_not_connected(self) -> None:
        """Disconnect on a never-connected client should not raise."""
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.disconnect()
        assert client.connected is False

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_disconnect_cancels_reconnect(self, mock_bus_class: MagicMock) -> None:
        mock_bus_class.return_value.connect = AsyncMock(side_effect=OSError("no bus"))

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()
        assert client._reconnect_handle is not None

        await client.disconnect()
        assert client._reconnect_handle is None


# ---------------------------------------------------------------------------
# DaemonClient — get_pull_requests
# ---------------------------------------------------------------------------


class TestGetPullRequests:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_returns_parsed_prs(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        json_str = _make_prs_json(_make_pr_dict(number=1), _make_pr_dict(number=2))
        interface.call_get_pull_requests = AsyncMock(return_value=json_str)

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()

        result = await client.get_pull_requests()

        assert len(result) == 2
        assert all(isinstance(pr, PRInfo) for pr in result)
        assert result[0].number == 1
        assert result[1].number == 2

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_dbus_error_returns_empty_and_disconnects(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)
        interface.call_get_pull_requests = AsyncMock(
            side_effect=DBusError("org.freedesktop.DBus.Error.NoReply", "timeout"),
        )

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        result = await client.get_pull_requests()

        assert result == []
        assert client.connected is False
        on_conn.assert_called_once_with(False)  # noqa: FBT003
        client._cancel_reconnect()

    async def test_not_connected_raises(self) -> None:
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        with pytest.raises(ConnectionError, match="Not connected"):
            await client.get_pull_requests()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_eoferror_returns_empty_and_disconnects(self, mock_bus_class: MagicMock) -> None:
        """EOFError during get_pull_requests is caught and triggers disconnect."""
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)
        interface.call_get_pull_requests = AsyncMock(side_effect=EOFError)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        result = await client.get_pull_requests()

        assert result == []
        assert client.connected is False
        client._cancel_reconnect()


# ---------------------------------------------------------------------------
# DaemonClient — get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_returns_parsed_status(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        json_str = _make_status_json(pr_count=3, last_updated=_NOW_ISO)
        interface.call_get_status = AsyncMock(return_value=json_str)

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()

        result = await client.get_status()

        assert isinstance(result, DaemonStatus)
        assert result.pr_count == 3
        assert result.last_updated == _NOW

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_dbus_error_returns_none_and_disconnects(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)
        interface.call_get_status = AsyncMock(
            side_effect=DBusError("org.freedesktop.DBus.Error.NoReply", "timeout"),
        )

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        result = await client.get_status()

        assert result is None
        assert client.connected is False
        client._cancel_reconnect()

    async def test_not_connected_raises(self) -> None:
        """get_status on a never-connected client raises ConnectionError."""
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        with pytest.raises(ConnectionError, match="Not connected"):
            await client.get_status()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_eoferror_returns_none_and_disconnects(self, mock_bus_class: MagicMock) -> None:
        """EOFError during get_status is caught and triggers disconnect."""
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)
        interface.call_get_status = AsyncMock(side_effect=EOFError)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        result = await client.get_status()

        assert result is None
        assert client.connected is False
        client._cancel_reconnect()


# ---------------------------------------------------------------------------
# DaemonClient — refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_returns_parsed_prs(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        json_str = _make_prs_json(_make_pr_dict(number=10))
        interface.call_refresh = AsyncMock(return_value=json_str)

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()

        result = await client.refresh()

        assert len(result) == 1
        assert result[0].number == 10

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_dbus_error_returns_empty_and_disconnects(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)
        interface.call_refresh = AsyncMock(side_effect=OSError("broken pipe"))

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        result = await client.refresh()

        assert result == []
        assert client.connected is False
        client._cancel_reconnect()

    async def test_not_connected_raises(self) -> None:
        """refresh on a never-connected client raises ConnectionError."""
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        with pytest.raises(ConnectionError, match="Not connected"):
            await client.refresh()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_eoferror_returns_empty_and_disconnects(self, mock_bus_class: MagicMock) -> None:
        """EOFError during refresh is caught and triggers disconnect."""
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)
        interface.call_refresh = AsyncMock(side_effect=EOFError)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        result = await client.refresh()

        assert result == []
        assert client.connected is False
        client._cancel_reconnect()


# ---------------------------------------------------------------------------
# DaemonClient — signal handling
# ---------------------------------------------------------------------------


class TestSignalHandling:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_signal_calls_on_prs_changed(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_prs = MagicMock()
        client = DaemonClient(on_prs_changed=on_prs, on_connection_changed=MagicMock())
        await client.connect()

        # Extract the signal callback that was registered
        signal_callback = interface.on_pull_requests_changed.call_args[0][0]

        # Simulate a signal
        json_str = _make_prs_json(_make_pr_dict(number=99))
        signal_callback(json_str)

        on_prs.assert_called_once()
        prs = on_prs.call_args[0][0]
        assert len(prs) == 1
        assert prs[0].number == 99

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_signal_with_invalid_json_does_not_crash(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_prs = MagicMock()
        client = DaemonClient(on_prs_changed=on_prs, on_connection_changed=MagicMock())
        await client.connect()

        signal_callback = interface.on_pull_requests_changed.call_args[0][0]

        # Malformed JSON should be logged, not raised
        signal_callback("not valid json")

        on_prs.assert_not_called()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_signal_with_missing_keys_does_not_crash(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_prs = MagicMock()
        client = DaemonClient(on_prs_changed=on_prs, on_connection_changed=MagicMock())
        await client.connect()

        signal_callback = interface.on_pull_requests_changed.call_args[0][0]

        # Valid JSON but missing required keys
        signal_callback('[{"url": "https://example.com"}]')

        on_prs.assert_not_called()


# ---------------------------------------------------------------------------
# DaemonClient — NameOwnerChanged detection
# ---------------------------------------------------------------------------


class TestNameOwnerChanged:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_daemon_disappearing_triggers_disconnect(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, _interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        # Extract the message handler that was registered
        message_handler = bus.add_message_handler.call_args[0][0]

        # Simulate a NameOwnerChanged signal where the daemon name loses its owner
        msg = MagicMock()
        msg.message_type = MessageType.SIGNAL
        msg.member = "NameOwnerChanged"
        msg.interface = "org.freedesktop.DBus"
        msg.body = [BUS_NAME, ":1.42", ""]  # name, old_owner, new_owner (empty = gone)

        result = message_handler(msg)

        assert result is False  # handler should not consume the message
        assert client.connected is False
        on_conn.assert_called_once_with(False)  # noqa: FBT003
        client._cancel_reconnect()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_other_name_change_ignored(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, _interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        message_handler = bus.add_message_handler.call_args[0][0]

        # NameOwnerChanged for a different bus name — should be ignored
        msg = MagicMock()
        msg.message_type = MessageType.SIGNAL
        msg.member = "NameOwnerChanged"
        msg.interface = "org.freedesktop.DBus"
        msg.body = ["org.some.OtherService", ":1.10", ""]

        message_handler(msg)

        assert client.connected is True
        on_conn.assert_not_called()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_name_acquiring_ignored(self, mock_bus_class: MagicMock) -> None:
        bus, _proxy, _interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        message_handler = bus.add_message_handler.call_args[0][0]

        # NameOwnerChanged where new_owner is non-empty (name acquired, not lost)
        msg = MagicMock()
        msg.message_type = MessageType.SIGNAL
        msg.member = "NameOwnerChanged"
        msg.interface = "org.freedesktop.DBus"
        msg.body = [BUS_NAME, "", ":1.99"]

        message_handler(msg)

        assert client.connected is True
        on_conn.assert_not_called()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_message_with_body_none_ignored(self, mock_bus_class: MagicMock) -> None:
        """NameOwnerChanged signal with body=None should be safely ignored."""
        bus, _proxy, _interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        message_handler = bus.add_message_handler.call_args[0][0]

        msg = MagicMock()
        msg.message_type = MessageType.SIGNAL
        msg.member = "NameOwnerChanged"
        msg.interface = "org.freedesktop.DBus"
        msg.body = None

        result = message_handler(msg)

        assert result is False
        assert client.connected is True
        on_conn.assert_not_called()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_message_with_short_body_ignored(self, mock_bus_class: MagicMock) -> None:
        """NameOwnerChanged signal with body shorter than 3 elements should be ignored."""
        bus, _proxy, _interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        message_handler = bus.add_message_handler.call_args[0][0]

        msg = MagicMock()
        msg.message_type = MessageType.SIGNAL
        msg.member = "NameOwnerChanged"
        msg.interface = "org.freedesktop.DBus"
        msg.body = [BUS_NAME]  # only 1 element, not 3

        result = message_handler(msg)

        assert result is False
        assert client.connected is True
        on_conn.assert_not_called()


# ---------------------------------------------------------------------------
# DaemonClient — reconnection logic
# ---------------------------------------------------------------------------


class TestReconnection:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_reconnect_scheduled_on_failure(self, mock_bus_class: MagicMock) -> None:
        mock_bus_class.return_value.connect = AsyncMock(side_effect=OSError("no bus"))

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()

        assert client._reconnect_handle is not None
        assert client._reconnect_handle.cancelled() is False
        client._cancel_reconnect()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_custom_reconnect_interval(self, mock_bus_class: MagicMock) -> None:
        """Custom reconnect_interval is stored and used by _schedule_reconnect."""
        mock_bus_class.return_value.connect = AsyncMock(side_effect=OSError("no bus"))

        client = DaemonClient(
            on_prs_changed=MagicMock(),
            on_connection_changed=MagicMock(),
            reconnect_interval=42,
        )
        assert client._reconnect_interval == 42

        await client.connect()
        assert client._reconnect_handle is not None
        client._cancel_reconnect()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_reconnect_not_doubled(self, mock_bus_class: MagicMock) -> None:
        """Multiple failures should not schedule multiple reconnects."""
        mock_bus_class.return_value.connect = AsyncMock(side_effect=OSError("no bus"))

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()

        first_handle = client._reconnect_handle
        # Manually trigger _set_disconnected again
        client._set_disconnected()

        # Should be the same handle (not replaced)
        assert client._reconnect_handle is first_handle
        client._cancel_reconnect()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_successful_connect_cancels_reconnect(self, mock_bus_class: MagicMock) -> None:
        """After a failed connect + scheduled reconnect, a successful connect should cancel it."""
        call_count = 0

        async def connect_side_effect() -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                msg = "no bus"
                raise OSError(msg)
            bus, _, _ = _make_mock_bus()
            return bus

        mock_bus_class.return_value.connect = AsyncMock(side_effect=connect_side_effect)

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()
        assert client._reconnect_handle is not None

        # Second attempt succeeds
        await client.connect()
        assert client._reconnect_handle is None
        assert client.connected is True

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_reconnect_retries_after_fired_timer_fails(self, mock_bus_class: MagicMock) -> None:
        """After a scheduled reconnect fires and connect() fails again, a new timer must be scheduled.

        Regression test: previously the stale (already-fired) TimerHandle was
        not cleared, so ``_schedule_reconnect()`` saw a non-None handle and
        returned immediately — permanently stopping the retry loop.
        """
        mock_bus_class.return_value.connect = AsyncMock(side_effect=OSError("no bus"))

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()  # first attempt fails, schedules reconnect

        first_handle = client._reconnect_handle
        assert first_handle is not None

        # Simulate the timer firing: the callback clears _reconnect_handle
        # then calls connect() which fails again.
        first_handle.cancel()  # prevent the real timer from firing
        client._reconnect_handle = None  # mimic what _fire() does
        await client.connect()  # second attempt also fails

        # A *new* reconnect must be scheduled (not stuck on the old handle).
        assert client._reconnect_handle is not None
        assert client._reconnect_handle is not first_handle
        client._cancel_reconnect()

    def test_cancel_reconnect_when_none(self) -> None:
        """Cancelling when no reconnect is scheduled should be a no-op."""
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        client._cancel_reconnect()  # should not raise
        assert client._reconnect_handle is None


# ---------------------------------------------------------------------------
# DaemonClient — _set_disconnected edge cases
# ---------------------------------------------------------------------------


class TestSetDisconnected:
    @patch("forgewatch.indicator.client.MessageBus")
    async def test_only_notifies_once_on_repeated_disconnect(self, mock_bus_class: MagicMock) -> None:
        """If already disconnected, _set_disconnected should not call on_connection_changed again."""
        bus, _proxy, _interface = _make_mock_bus()
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        on_conn = MagicMock()
        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=on_conn)
        await client.connect()
        on_conn.reset_mock()

        client._set_disconnected()
        client._set_disconnected()  # second call

        # on_connection_changed(False) should only be called once
        on_conn.assert_called_once_with(False)  # noqa: FBT003
        client._cancel_reconnect()

    @patch("forgewatch.indicator.client.MessageBus")
    async def test_bus_disconnect_error_is_swallowed(self, mock_bus_class: MagicMock) -> None:
        """If bus.disconnect() raises, it should be caught and not propagate."""
        bus, _proxy, _interface = _make_mock_bus()
        bus.disconnect = MagicMock(side_effect=RuntimeError("already closed"))
        mock_bus_class.return_value.connect = AsyncMock(return_value=bus)

        client = DaemonClient(on_prs_changed=MagicMock(), on_connection_changed=MagicMock())
        await client.connect()

        # Should not raise
        client._set_disconnected()
        assert client.connected is False
        client._cancel_reconnect()

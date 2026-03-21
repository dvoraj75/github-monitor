"""Async D-Bus client for the forgewatch daemon.

Connects to the session bus, subscribes to the ``PullRequestsChanged``
signal, and exposes methods to query PR state or trigger a refresh.
Handles reconnection automatically when the daemon is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import MessageType
from dbus_next.errors import DBusError

from forgewatch.constants import BUS_NAME, INTERFACE_NAME, OBJECT_PATH

from .models import DaemonStatus, PRInfo

if TYPE_CHECKING:
    from collections.abc import Callable

    from dbus_next.aio.proxy_object import ProxyInterface
    from dbus_next.message import Message

logger = logging.getLogger(__name__)

_RECONNECT_INTERVAL_S = 10


# ---------------------------------------------------------------------------
# JSON → dataclass parsing helpers
# ---------------------------------------------------------------------------


def _parse_pr(data: dict[str, object]) -> PRInfo:
    """Parse a single PR dict from the daemon's JSON into a PRInfo."""
    return PRInfo(
        url=str(data["url"]),
        title=str(data["title"]),
        repo=str(data["repo"]),
        author=str(data["author"]),
        author_avatar_url=str(data["author_avatar_url"]),
        number=int(data["number"]),  # type: ignore[call-overload]
        updated_at=datetime.fromisoformat(str(data["updated_at"])),
        review_requested=bool(data["review_requested"]),
        assigned=bool(data["assigned"]),
    )


def _parse_prs(json_str: str) -> list[PRInfo]:
    """Parse a JSON array string into a list of PRInfo dataclasses."""
    raw: list[dict[str, object]] = json.loads(json_str)
    return [_parse_pr(item) for item in raw]


def _parse_status(json_str: str) -> DaemonStatus:
    """Parse a JSON object string into a DaemonStatus dataclass."""
    raw: dict[str, object] = json.loads(json_str)
    last_updated_raw = raw.get("last_updated")
    return DaemonStatus(
        pr_count=int(raw["pr_count"]),  # type: ignore[call-overload]
        last_updated=datetime.fromisoformat(str(last_updated_raw)) if last_updated_raw else None,
    )


# ---------------------------------------------------------------------------
# D-Bus client
# ---------------------------------------------------------------------------


class DaemonClient:
    """Async D-Bus client for the forgewatch daemon.

    Connects to the session bus, obtains a proxy for the daemon's D-Bus
    interface, and subscribes to the ``PullRequestsChanged`` signal.
    If the daemon is not running (or disappears), the client automatically
    retries the connection after the configured reconnect interval.
    """

    def __init__(
        self,
        on_prs_changed: Callable[[list[PRInfo]], None],
        on_connection_changed: Callable[[bool], None],
        *,
        reconnect_interval: int = _RECONNECT_INTERVAL_S,
    ) -> None:
        self._on_prs_changed = on_prs_changed
        self._on_connection_changed = on_connection_changed
        self._reconnect_interval = reconnect_interval

        self._bus: MessageBus | None = None
        self._interface: ProxyInterface | None = None
        self._connected: bool = False
        self._reconnect_handle: asyncio.TimerHandle | None = None

    # -- public API --------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the client is currently connected to the daemon."""
        return self._connected

    async def connect(self) -> None:
        """Connect to the daemon over D-Bus.

        On failure (daemon not running, bus error), the client marks
        itself as disconnected and schedules a reconnection attempt.
        """
        try:
            bus = await MessageBus().connect()
            introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
            proxy = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
            interface = proxy.get_interface(INTERFACE_NAME)

            # Subscribe to the PullRequestsChanged signal for live updates.
            # dbus-next generates signal subscription methods dynamically
            # from introspection data — they don't exist in static type stubs.
            interface.on_pull_requests_changed(self._on_signal)  # type: ignore[attr-defined]

            # Watch for the daemon's bus name disappearing so we can
            # detect when the daemon exits or crashes.
            bus.add_message_handler(self._on_message)

            self._bus = bus
            self._interface = interface
            self._connected = True
            self._cancel_reconnect()
            logger.info("Connected to daemon over D-Bus")
            self._on_connection_changed(True)  # noqa: FBT003

        except (DBusError, OSError) as exc:
            logger.warning("Failed to connect to daemon: %s", exc)
            self._set_disconnected()

    async def disconnect(self) -> None:
        """Disconnect from D-Bus and cancel any pending reconnection."""
        self._cancel_reconnect()
        if self._bus is not None:
            self._bus.disconnect()  # type: ignore[no-untyped-call]
            self._bus = None
        self._interface = None
        self._connected = False

    async def get_pull_requests(self) -> list[PRInfo]:
        """Fetch all currently tracked PRs from the daemon."""
        interface = self._require_interface()
        try:
            result: str = await interface.call_get_pull_requests()  # type: ignore[attr-defined]
        except (DBusError, OSError, EOFError) as exc:
            logger.warning("get_pull_requests failed: %s", exc)
            self._set_disconnected()
            return []
        return _parse_prs(result)

    async def get_status(self) -> DaemonStatus | None:
        """Fetch daemon status metadata.

        Returns ``None`` if the call fails (e.g. daemon went away).
        """
        interface = self._require_interface()
        try:
            result: str = await interface.call_get_status()  # type: ignore[attr-defined]
        except (DBusError, OSError, EOFError) as exc:
            logger.warning("get_status failed: %s", exc)
            self._set_disconnected()
            return None
        return _parse_status(result)

    async def refresh(self) -> list[PRInfo]:
        """Trigger an immediate poll and return the updated PR list.

        Returns an empty list if the call fails.
        """
        interface = self._require_interface()
        try:
            result: str = await interface.call_refresh()  # type: ignore[attr-defined]
        except (DBusError, OSError, EOFError) as exc:
            logger.warning("refresh failed: %s", exc)
            self._set_disconnected()
            return []
        return _parse_prs(result)

    # -- internal ----------------------------------------------------------

    def _require_interface(self) -> ProxyInterface:
        """Return the D-Bus interface proxy or raise if not connected."""
        if self._interface is None:
            msg = "Not connected to daemon"
            raise ConnectionError(msg)
        return self._interface

    def _on_signal(self, json_str: str) -> None:
        """Handle the ``PullRequestsChanged`` D-Bus signal."""
        try:
            prs = _parse_prs(json_str)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            logger.exception("Failed to parse PullRequestsChanged payload")
            return
        self._on_prs_changed(prs)

    def _on_message(self, msg: Message) -> bool:
        """Low-level message handler to detect daemon name disappearance.

        Watches for ``NameOwnerChanged`` signals from the D-Bus daemon
        itself.  When the daemon's bus name loses its owner (new_owner
        is empty), we know the daemon has exited.

        Returns ``False`` so other handlers can still process the message.
        """
        if (
            msg.message_type == MessageType.SIGNAL
            and msg.member == "NameOwnerChanged"
            and msg.interface == "org.freedesktop.DBus"
            and msg.body is not None
            and len(msg.body) >= 3  # noqa: PLR2004
            and msg.body[0] == BUS_NAME
            and msg.body[2] == ""
        ):
            logger.warning("Daemon bus name '%s' lost its owner", BUS_NAME)
            self._set_disconnected()
        return False

    def _set_disconnected(self) -> None:
        """Mark the client as disconnected, notify the callback, and schedule reconnect."""
        was_connected = self._connected
        self._interface = None
        self._connected = False

        if self._bus is not None:
            try:
                self._bus.disconnect()  # type: ignore[no-untyped-call]
            except Exception:  # noqa: BLE001
                logger.debug("Error disconnecting bus", exc_info=True)
            self._bus = None

        if was_connected:
            self._on_connection_changed(False)  # noqa: FBT003
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt after the configured reconnect interval."""
        if self._reconnect_handle is not None:
            return  # already scheduled
        loop = asyncio.get_running_loop()

        def _fire() -> None:
            # Clear the handle *before* attempting to reconnect so that
            # a failed connect() -> _set_disconnected() -> _schedule_reconnect()
            # chain can schedule a fresh timer instead of bailing out.
            self._reconnect_handle = None
            asyncio.ensure_future(self.connect())  # noqa: RUF006

        self._reconnect_handle = loop.call_later(self._reconnect_interval, _fire)
        logger.debug("Reconnect scheduled in %ds", self._reconnect_interval)

    def _cancel_reconnect(self) -> None:
        """Cancel a pending reconnection attempt, if any."""
        if self._reconnect_handle is not None:
            self._reconnect_handle.cancel()
            self._reconnect_handle = None

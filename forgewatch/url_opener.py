from __future__ import annotations

import asyncio
import logging

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import MessageType
from dbus_next.errors import DBusError
from dbus_next.message import Message

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = frozenset(("http", "https"))


# XDG Desktop Portal D-Bus coordinates.  The portal allows sandboxed
# processes (systemd services, Flatpak, Snap) to open URLs in the
# user's default browser without inheriting the caller's restrictions.
_PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
_PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_INTERFACE = "org.freedesktop.portal.OpenURI"


async def open_url(url: str) -> None:
    """Open *url* in the default browser.

    Only ``http`` and ``https`` URLs are accepted.  Any other scheme is
    rejected with a warning to prevent opening arbitrary protocols via
    ``xdg-open`` or the XDG Desktop Portal.

    Tries the XDG Desktop Portal first (works from sandboxed systemd
    services), then falls back to ``xdg-open`` for environments where
    the portal is unavailable (e.g. minimal window managers).
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        logger.warning("Rejected URL with disallowed scheme %r: %s", parsed.scheme, url)
        return
    if await _open_url_portal(url):
        return
    await _open_url_xdg(url)


async def _open_url_portal(url: str) -> bool:
    """Open *url* via the XDG Desktop Portal over D-Bus.

    Sends a raw D-Bus method call instead of using ``bus.introspect()``
    + proxy objects.  This avoids a ``dbus-next`` bug where introspecting
    the portal object fails because other interfaces on that path expose
    property names with hyphens (e.g. ``power-saver-enabled``), which
    ``dbus-next`` rejects as invalid member names.

    Returns ``True`` on success, ``False`` on any failure.
    """
    bus: MessageBus | None = None
    try:
        bus = await MessageBus().connect()
        msg = Message(
            destination=_PORTAL_BUS_NAME,
            path=_PORTAL_OBJECT_PATH,
            interface=_PORTAL_INTERFACE,
            member="OpenURI",
            signature="ssa{sv}",
            body=["", url, {}],
        )
        reply = await bus.call(msg)
        if reply is None:
            logger.debug("XDG Desktop Portal returned no reply for %s", url)
            return False
        if reply.message_type == MessageType.ERROR:
            logger.debug(
                "XDG Desktop Portal error for %s: %s %s",
                url,
                reply.error_name,
                reply.body,
            )
            return False
        logger.debug("Opened URL via XDG Desktop Portal: %s", url)
    except (DBusError, OSError, ValueError, TimeoutError) as exc:
        logger.debug("XDG Desktop Portal unavailable, will try xdg-open: %s", exc)
        return False
    else:
        return True
    finally:
        if bus is not None:
            bus.disconnect()  # type: ignore[no-untyped-call]


async def _open_url_xdg(url: str) -> None:
    """Open *url* via ``xdg-open`` as a fallback."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "xdg-open",
            url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "xdg-open failed (exit %d) for URL %s: %s",
                proc.returncode,
                url,
                stderr.decode().strip(),
            )
        else:
            logger.debug("Opened URL via xdg-open: %s", url)
    except FileNotFoundError:
        logger.warning("xdg-open not found. Cannot open URL: %s", url)
    except OSError:
        logger.debug("Error opening URL %s", url, exc_info=True)

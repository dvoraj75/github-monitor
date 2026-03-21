"""D-Bus interface for exposing daemon state on the session bus.

Exports a service interface under the well-known name
``org.forgewatch.Daemon`` at object path
``/org/forgewatch/Daemon``.  External tools (panel plugins, CLI
scripts) can call methods to query PR state or trigger a refresh, and
subscribe to the ``PullRequestsChanged`` signal for live updates.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from dbus_next.aio.message_bus import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .constants import BUS_NAME, INTERFACE_NAME, OBJECT_PATH

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .poller import PullRequest
    from .store import PRStore, StoreStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialize_pr(pr: PullRequest) -> dict[str, Any]:
    """Convert a PullRequest to a JSON-serialisable dict."""
    return {
        "url": pr.url,
        "title": pr.title,
        "repo": pr.repo_full_name,
        "author": pr.author,
        "author_avatar_url": pr.author_avatar_url,
        "number": pr.number,
        "updated_at": pr.updated_at.isoformat(),
        "review_requested": pr.review_requested,
        "assigned": pr.assigned,
    }


def _serialize_prs(prs: list[PullRequest]) -> str:
    """Serialise a list of PullRequests to a JSON string."""
    return json.dumps([_serialize_pr(pr) for pr in prs])


def _serialize_status(status: StoreStatus) -> str:
    """Serialise a StoreStatus to a JSON string."""
    return json.dumps(
        {
            "pr_count": status.pr_count,
            "last_updated": status.last_updated.isoformat() if status.last_updated else None,
        }
    )


# ---------------------------------------------------------------------------
# D-Bus service interface
# ---------------------------------------------------------------------------


class ForgewatchInterface(ServiceInterface):
    """D-Bus interface: ``org.forgewatch.Daemon``.

    Provides methods for querying PR state and triggering a refresh, plus
    a signal emitted whenever the PR list changes.
    """

    def __init__(
        self,
        store: PRStore,
        poll_callback: Callable[[], Awaitable[None]],
    ) -> None:
        super().__init__(INTERFACE_NAME)
        self._store = store
        self._poll_callback = poll_callback

    # -- methods -------------------------------------------------------------

    @method()  # type: ignore[untyped-decorator]
    def GetPullRequests(self) -> "s":  # type: ignore[name-defined]  # noqa: N802, F821, UP037
        """Return a JSON array of all currently tracked PRs.

        Each element contains: ``url``, ``title``, ``repo``, ``author``,
        ``number``, ``updated_at``, ``review_requested``, ``assigned``.
        """
        return _serialize_prs(self._store.get_all())

    @method()  # type: ignore[untyped-decorator]
    def GetStatus(self) -> "s":  # type: ignore[name-defined]  # noqa: N802, F821, UP037
        """Return a JSON object with store metadata.

        Contains: ``pr_count``, ``last_updated``.
        """
        return _serialize_status(self._store.get_status())

    @method()  # type: ignore[untyped-decorator]
    async def Refresh(self) -> "s":  # type: ignore[name-defined]  # noqa: N802, F821, UP037
        """Trigger an immediate poll and return the updated PR list."""
        logger.info("D-Bus Refresh() called — triggering poll")
        await self._poll_callback()
        return _serialize_prs(self._store.get_all())

    # -- signals -------------------------------------------------------------

    @signal()  # type: ignore[untyped-decorator]
    def PullRequestsChanged(self) -> "s":  # type: ignore[name-defined]  # noqa: N802, F821, UP037
        """Signal emitted when the PR list changes.

        Carries a JSON array of all current PRs (same format as
        ``GetPullRequests``).
        """
        return _serialize_prs(self._store.get_all())


# ---------------------------------------------------------------------------
# Bus setup
# ---------------------------------------------------------------------------


async def setup_dbus(
    store: PRStore,
    poll_callback: Callable[[], Awaitable[None]],
) -> tuple[MessageBus, ForgewatchInterface]:
    """Connect to the session bus, export the interface, and request the name.

    Returns the connected :class:`MessageBus` and the exported
    :class:`ForgewatchInterface` so the caller can emit signals and
    disconnect cleanly on shutdown.
    """
    bus = await MessageBus().connect()
    interface = ForgewatchInterface(store, poll_callback)
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    logger.info("D-Bus service exported as %s at %s", BUS_NAME, OBJECT_PATH)
    return bus, interface

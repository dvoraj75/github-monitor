"""Application orchestrator for the forgewatch indicator.

Wires together the D-Bus client, system tray icon, and popup window
into a running application.  Uses ``gbulb`` to run both GTK (GLib main
loop) and asyncio (``dbus-next``) in a single thread.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING

from forgewatch.url_opener import open_url

from .client import DaemonClient

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from .models import DaemonStatus, PRInfo
    from .tray import TrayIcon
    from .window import PRWindow

logger = logging.getLogger(__name__)


class IndicatorApp:
    """Main application that bridges D-Bus, tray icon, and popup window.

    The lifecycle is:

    1. ``run()`` — create components, register signal handlers, connect
       to the daemon, enter the GLib/asyncio event loop.
    2. Event loop — GTK events (menu clicks, window interactions) and
       asyncio coroutines (D-Bus calls) run cooperatively via ``gbulb``.
    3. ``shutdown()`` — disconnect from D-Bus, clean up resources.
    """

    def __init__(
        self,
        *,
        icon_theme: str = "light",
        reconnect_interval: int = 10,
        window_width: int = 400,
        max_window_height: int = 500,
    ) -> None:
        # Lazy imports — tray and window depend on GTK system packages
        # that are unavailable in headless CI environments.
        from .tray import TrayIcon  # noqa: PLC0415
        from .window import PRWindow  # noqa: PLC0415

        self._current_prs: list[PRInfo] = []
        self._current_status: DaemonStatus | None = None
        self._shutdown_event = asyncio.Event()

        # Background tasks scheduled from synchronous callbacks.
        # Stored in a set to prevent garbage collection before completion.
        self._tasks: set[asyncio.Task[None]] = set()

        self._client = DaemonClient(
            on_prs_changed=self._on_prs_changed,
            on_connection_changed=self._on_connection_changed,
            reconnect_interval=reconnect_interval,
        )
        self._tray: TrayIcon = TrayIcon(
            on_activate=self._on_activate,
            on_refresh=self._on_refresh,
            on_quit=self._on_quit,
            icon_theme=icon_theme,
        )
        self._window: PRWindow = PRWindow(
            on_pr_clicked=self._on_pr_clicked,
            on_refresh=self._on_refresh,
            on_visibility_changed=self._on_window_visibility_changed,
            window_width=window_width,
            max_window_height=max_window_height,
        )

    # -- public lifecycle ----------------------------------------------------

    async def run(self) -> None:
        """Start the indicator and run until shutdown is requested.

        Assumes ``gbulb.install()`` has already been called by the
        entry point so the asyncio event loop is GLib-based.
        """
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, self._shutdown_event.set)
        loop.add_signal_handler(signal.SIGINT, self._shutdown_event.set)

        await self._client.connect()

        if self._client.connected:
            await self._fetch_and_update()

        logger.info("Indicator started")
        await self._shutdown_event.wait()
        logger.info("Shutdown requested")

    async def shutdown(self) -> None:
        """Clean up resources after the event loop exits."""
        # Cancel any pending background tasks.
        for task in self._tasks:
            task.cancel()

        await self._client.disconnect()
        logger.info("Indicator stopped")

    # -- D-Bus client callbacks (synchronous) --------------------------------

    def _on_prs_changed(self, prs: list[PRInfo]) -> None:
        """Handle the ``PullRequestsChanged`` D-Bus signal.

        Called synchronously from the D-Bus signal handler.  Schedules
        an async task to fetch fresh status and update the UI.
        """
        self._current_prs = prs
        self._schedule(self._handle_prs_changed(prs))

    def _on_connection_changed(self, connected: bool) -> None:  # noqa: FBT001
        """Handle daemon connection/disconnection.

        Called synchronously from the D-Bus client.  Schedules an
        async task for the connected case (which needs to fetch PRs).
        """
        self._tray.set_connected(connected=connected)
        if connected:
            self._schedule(self._handle_connected())
        else:
            self._current_prs = []
            self._current_status = None
            self._tray.set_pr_count(0, has_review_requested=False)
            self._window.set_disconnected()

    # -- UI callbacks (synchronous) ------------------------------------------

    def _on_activate(self) -> None:
        """Toggle the popup window visibility (tray 'Show PRs' click)."""
        self._window.toggle()

    def _on_window_visibility_changed(self, visible: bool) -> None:  # noqa: FBT001
        """Update the tray menu label when the window is shown or hidden."""
        self._tray.set_window_visible(visible=visible)

    def _on_refresh(self) -> None:
        """Trigger a daemon refresh (tray or window refresh button)."""
        if not self._client.connected:
            logger.debug("Refresh requested but not connected to daemon")
            return
        self._schedule(self._handle_refresh())

    def _on_pr_clicked(self, url: str) -> None:
        """Open a PR URL in the browser and hide the popup."""
        self._window.hide()
        self._schedule(self._handle_open_url(url))

    def _on_quit(self) -> None:
        """Quit the indicator (tray 'Quit' menu item)."""
        self._shutdown_event.set()

    # -- async handlers scheduled from sync callbacks ------------------------

    async def _handle_prs_changed(self, prs: list[PRInfo]) -> None:
        """Update tray and window after receiving new PR data."""
        status = await self._fetch_status()
        self._update_ui(prs, status)

    async def _handle_connected(self) -> None:
        """Fetch initial state after (re)connecting to the daemon."""
        await self._fetch_and_update()

    async def _handle_refresh(self) -> None:
        """Call daemon Refresh() and update the UI with results."""
        try:
            prs = await self._client.refresh()
        except Exception:  # noqa: BLE001
            logger.warning("Refresh failed", exc_info=True)
            return

        self._current_prs = prs
        status = await self._fetch_status()
        self._update_ui(prs, status)

    async def _handle_open_url(self, url: str) -> None:
        """Open a URL in the default browser."""
        try:
            await open_url(url)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to open URL: %s", url, exc_info=True)

    # -- internal helpers ----------------------------------------------------

    async def _fetch_and_update(self) -> None:
        """Fetch current PRs and status from the daemon and update the UI."""
        try:
            prs = await self._client.get_pull_requests()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to fetch initial PRs", exc_info=True)
            return

        self._current_prs = prs
        status = await self._fetch_status()
        self._update_ui(prs, status)

    async def _fetch_status(self) -> DaemonStatus | None:
        """Fetch daemon status, falling back to the cached value on error."""
        try:
            status = await self._client.get_status()
            self._current_status = status
        except Exception:  # noqa: BLE001
            logger.debug("Failed to fetch daemon status", exc_info=True)
            status = self._current_status
        return status

    def _update_ui(self, prs: list[PRInfo], status: DaemonStatus | None) -> None:
        """Push PR data to the tray icon and popup window."""
        has_review = any(pr.review_requested for pr in prs)
        self._tray.set_pr_count(len(prs), has_review_requested=has_review)
        self._window.update_prs(prs, status)

    def _schedule(self, coro: Coroutine[object, object, None]) -> None:
        """Schedule an async coroutine from a synchronous callback.

        The task reference is stored in ``_tasks`` to prevent garbage
        collection before the coroutine completes.
        """
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        """Remove a completed task and log any unexpected exceptions."""
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Unhandled error in background task", exc_info=exc)

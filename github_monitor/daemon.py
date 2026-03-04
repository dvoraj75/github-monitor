"""Main daemon loop: wires together poller, store, D-Bus, and notifier.

Handles the asyncio event loop, periodic polling, Unix signal handling
(SIGTERM / SIGINT for shutdown, SIGHUP for config reload), and clean
resource teardown.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING

from .config import load_config
from .dbus_service import setup_dbus
from .notifier import notify_new_prs
from .poller import GitHubClient
from .store import PRStore

if TYPE_CHECKING:
    from pathlib import Path

    from dbus_next.aio.message_bus import MessageBus

    from .config import Config
    from .dbus_service import GithubMonitorInterface

logger = logging.getLogger(__name__)


class Daemon:
    """Orchestrates all components into a running daemon.

    The lifecycle is:

    1. ``start()`` — initialise HTTP session, register D-Bus service,
       install Unix signal handlers, enter the poll loop.
    2. ``_poll_loop()`` — repeatedly call ``_poll_once()`` then wait for
       the configured interval (or an early wake-up from a shutdown /
       refresh signal).
    3. ``stop()`` — close the HTTP session and disconnect from D-Bus.
    """

    def __init__(self, config: Config, config_path: Path | None = None) -> None:
        self.config = config
        self.config_path = config_path
        self.store = PRStore()
        self.client = GitHubClient(
            token=config.github_token,
            username=config.github_username,
            repos=config.repos,
            base_url=config.github_base_url,
            max_retries=config.max_retries,
        )
        self.bus: MessageBus | None = None
        self.interface: GithubMonitorInterface | None = None
        self._running = False
        self._first_poll = True
        self._shutdown_event = asyncio.Event()
        self._reload_event = asyncio.Event()

    # -- public lifecycle ----------------------------------------------------

    async def start(self) -> None:
        """Initialise all components and start the poll loop."""
        # 1. Start GitHub client (creates aiohttp session)
        await self.client.start()

        # 2. Set up D-Bus (if enabled)
        if self.config.dbus_enabled:
            self.bus, self.interface = await setup_dbus(
                self.store,
                self._poll_once,
            )
        else:
            logger.info("D-Bus disabled by configuration")

        # 3. Register signal handlers
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, self._handle_shutdown)
        loop.add_signal_handler(signal.SIGINT, self._handle_shutdown)
        loop.add_signal_handler(signal.SIGHUP, self._handle_reload)

        # 4. Start polling
        self._running = True
        logger.info(
            "Daemon started. Polling every %d seconds.",
            self.config.poll_interval,
        )
        await self._poll_loop()

    async def stop(self) -> None:
        """Clean shutdown: close HTTP session and disconnect D-Bus."""
        await self.client.close()
        if self.bus:
            self.bus.disconnect()  # type: ignore[no-untyped-call]
        logger.info("Daemon stopped")

    # -- poll loop -----------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Main polling loop with immediate-shutdown support.

        Uses an :class:`asyncio.Event` so that a SIGTERM / SIGINT can
        wake the sleep immediately rather than waiting up to
        ``poll_interval`` seconds.
        """
        while self._running:
            await self._poll_once()

            shutdown_task = asyncio.create_task(self._shutdown_event.wait())
            reload_task = asyncio.create_task(self._reload_event.wait())
            try:
                done, _ = await asyncio.wait(
                    {shutdown_task, reload_task},
                    timeout=self.config.poll_interval,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for t in (shutdown_task, reload_task):
                    if not t.done():
                        t.cancel()
                await asyncio.gather(shutdown_task, reload_task, return_exceptions=True)

            if shutdown_task in done:
                break

            if reload_task in done:
                self._reload_event.clear()

    async def _poll_once(self) -> None:
        """Single poll cycle: fetch -> diff -> notify -> signal."""
        try:
            prs = await self.client.fetch_all()
            diff = self.store.update(prs)

            should_notify = (
                diff.new_prs
                and self.config.notifications_enabled
                and (not self._first_poll or self.config.notify_on_first_poll)
            )
            if should_notify:
                await notify_new_prs(
                    diff.new_prs,
                    threshold=self.config.notification_threshold,
                    urgency=self.config.notification_urgency,
                )

            if diff.has_changes and self.interface is not None:
                self.interface.PullRequestsChanged()

            if self._first_poll:
                self._first_poll = False
                logger.info(
                    "Initial poll complete: %d PRs found",
                    len(prs),
                )
            else:
                logger.debug(
                    "Poll complete: %d PRs (+%d/-%d/~%d)",
                    len(prs),
                    len(diff.new_prs),
                    len(diff.closed_prs),
                    len(diff.updated_prs),
                )
        except Exception:
            logger.exception("Error during poll cycle")

    # -- signal handlers -----------------------------------------------------

    def _handle_shutdown(self) -> None:
        """Handle SIGTERM / SIGINT — request graceful shutdown."""
        logger.info("Shutdown signal received")
        self._running = False
        self._shutdown_event.set()

    def _handle_reload(self) -> None:
        """Handle SIGHUP — schedule an async config reload.

        Signal handlers cannot be async, so we schedule the actual
        reload work as a task on the running event loop.
        """
        logger.info("Reload signal received")
        loop = asyncio.get_running_loop()
        task = loop.create_task(self._reload_config())
        # Prevent the task from being garbage-collected before completion.
        task.add_done_callback(lambda _t: None)

    async def _reload_config(self) -> None:
        """Reload configuration and recreate the HTTP session.

        After ``update_config()`` the aiohttp session headers are stale
        (they still carry the old token).  We close and restart the
        session so that changes — especially a new token — take effect
        immediately.
        """
        try:
            self.config = load_config(self.config_path)

            # Apply log level change immediately
            logging.getLogger().setLevel(
                getattr(logging, self.config.log_level.upper()),
            )

            await self.client.close()
            self.client.update_config(
                token=self.config.github_token,
                username=self.config.github_username,
                repos=self.config.repos,
                base_url=self.config.github_base_url,
                max_retries=self.config.max_retries,
            )
            await self.client.start()
            self._reload_event.set()
            logger.info("Config reloaded successfully")
        except Exception:
            logger.exception("Failed to reload config")

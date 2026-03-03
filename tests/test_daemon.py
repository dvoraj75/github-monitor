"""Tests for github_monitor.daemon."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from github_monitor.config import Config
from github_monitor.daemon import Daemon
from github_monitor.poller import PullRequest
from github_monitor.store import StateDiff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


def _make_config(**overrides: object) -> Config:
    """Build a Config with sensible test defaults."""
    defaults = {
        "github_token": "ghp_test1234567890",
        "github_username": "testuser",
        "poll_interval": 300,
        "repos": [],
    }
    defaults.update(overrides)
    return Config(**defaults)  # type: ignore[arg-type]


def _make_pr(
    number: int = 1,
    repo: str = "owner/repo",
    *,
    title: str = "Fix bug",
    author: str = "alice",
) -> PullRequest:
    """Build a PullRequest for testing."""
    return PullRequest(
        url=f"https://github.com/{repo}/pull/{number}",
        api_url=f"https://api.github.com/repos/{repo}/pulls/{number}",
        title=title,
        repo_full_name=repo,
        author=author,
        author_avatar_url=f"https://avatars.githubusercontent.com/u/{number}",
        number=number,
        updated_at=_NOW,
        review_requested=True,
        assigned=False,
    )


def _empty_diff() -> StateDiff:
    """Return a StateDiff with no changes."""
    return StateDiff()


def _new_diff(prs: list[PullRequest]) -> StateDiff:
    """Return a StateDiff with new PRs only."""
    return StateDiff(new_prs=prs)


def _closed_diff(prs: list[PullRequest]) -> StateDiff:
    """Return a StateDiff with closed PRs only."""
    return StateDiff(closed_prs=prs)


def _updated_diff(prs: list[PullRequest]) -> StateDiff:
    """Return a StateDiff with updated PRs only."""
    return StateDiff(updated_prs=prs)


# ---------------------------------------------------------------------------
# Tests: Daemon construction
# ---------------------------------------------------------------------------


class TestDaemonInit:
    """Daemon constructor should wire up components correctly."""

    def test_creates_store_and_client(self) -> None:
        config = _make_config()
        daemon = Daemon(config)
        assert daemon.store is not None
        assert daemon.client is not None
        assert daemon.config is config

    def test_initial_state_flags(self) -> None:
        daemon = Daemon(_make_config())
        assert daemon._running is False
        assert daemon._first_poll is True
        assert daemon.bus is None
        assert daemon.interface is None

    def test_config_path_defaults_to_none(self) -> None:
        daemon = Daemon(_make_config())
        assert daemon.config_path is None

    def test_stores_config_path(self) -> None:
        path = Path("/custom/config.toml")
        daemon = Daemon(_make_config(), config_path=path)
        assert daemon.config_path is path

    def test_client_receives_config_values(self) -> None:
        config = _make_config(
            github_token="ghp_custom",
            github_username="janedoe",
            repos=["org/repo1"],
        )
        daemon = Daemon(config)
        assert daemon.client._token == "ghp_custom"
        assert daemon.client._username == "janedoe"
        assert daemon.client._repos == ["org/repo1"]


# ---------------------------------------------------------------------------
# Tests: single poll cycle
# ---------------------------------------------------------------------------


class TestPollOnce:
    """_poll_once should orchestrate fetch -> diff -> notify -> signal."""

    async def test_fetches_and_updates_store(self) -> None:
        daemon = Daemon(_make_config())
        prs = [_make_pr(1), _make_pr(2)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        await daemon._poll_once()

        daemon.client.fetch_all.assert_awaited_once()
        assert daemon.store.get_status().pr_count == 2

    async def test_notifies_on_new_prs(self) -> None:
        daemon = Daemon(_make_config())
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_awaited_once_with(
                prs,
                threshold=3,
                urgency="normal",
            )

    async def test_suppresses_notifications_on_first_poll(self) -> None:
        daemon = Daemon(_make_config())
        prs = [_make_pr(1), _make_pr(2)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        assert daemon._first_poll is True

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_not_awaited()

    async def test_clears_first_poll_flag_after_first_cycle(self) -> None:
        daemon = Daemon(_make_config())
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        assert daemon._first_poll is True

        await daemon._poll_once()

        assert daemon._first_poll is False

    async def test_emits_signal_on_changes(self) -> None:
        daemon = Daemon(_make_config())
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        await daemon._poll_once()

        daemon.interface.PullRequestsChanged.assert_called_once()

    async def test_emits_signal_on_first_poll_too(self) -> None:
        daemon = Daemon(_make_config())
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        assert daemon._first_poll is True

        await daemon._poll_once()

        daemon.interface.PullRequestsChanged.assert_called_once()

    async def test_no_signal_when_no_changes(self) -> None:
        daemon = Daemon(_make_config())
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        # Prime the store with empty state (first poll already happened)
        daemon.store.update([])

        await daemon._poll_once()

        daemon.interface.PullRequestsChanged.assert_not_called()

    async def test_no_notification_when_no_new_prs(self) -> None:
        daemon = Daemon(_make_config())
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_not_awaited()

    async def test_signal_on_closed_prs(self) -> None:
        daemon = Daemon(_make_config())
        daemon.interface = MagicMock()
        daemon._first_poll = False

        # Prime store with one PR
        daemon.store.update([_make_pr(1)])

        # Now return empty — the PR is "closed"
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]
        await daemon._poll_once()

        daemon.interface.PullRequestsChanged.assert_called_once()

    async def test_exception_is_caught_and_logged(self) -> None:
        daemon = Daemon(_make_config())
        daemon.client.fetch_all = AsyncMock(side_effect=RuntimeError("API error"))  # type: ignore[method-assign]
        daemon.interface = MagicMock()

        # Should not raise
        with patch("github_monitor.daemon.logger") as mock_logger:
            await daemon._poll_once()
            mock_logger.exception.assert_called_once()

    async def test_handles_none_interface_gracefully(self) -> None:
        daemon = Daemon(_make_config())
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = None
        daemon._first_poll = False

        # Should not raise even though interface is None
        await daemon._poll_once()

        assert daemon.store.get_status().pr_count == 1


# ---------------------------------------------------------------------------
# Tests: graceful shutdown
# ---------------------------------------------------------------------------


class TestHandleShutdown:
    """_handle_shutdown should stop the daemon gracefully."""

    def test_sets_running_false(self) -> None:
        daemon = Daemon(_make_config())
        daemon._running = True

        daemon._handle_shutdown()

        assert daemon._running is False

    def test_sets_shutdown_event(self) -> None:
        daemon = Daemon(_make_config())

        daemon._handle_shutdown()

        assert daemon._shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Tests: config reload
# ---------------------------------------------------------------------------


class TestReloadConfig:
    """_reload_config should reload config and recreate the HTTP session."""

    async def test_reloads_config_and_restarts_session(self) -> None:
        daemon = Daemon(_make_config())
        new_config = _make_config(
            github_token="ghp_new_token",
            github_username="newuser",
            repos=["new/repo"],
        )
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]

        with patch("github_monitor.daemon.load_config", return_value=new_config) as mock_load:
            await daemon._reload_config()

        mock_load.assert_called_once_with(None)
        assert daemon.config is new_config
        daemon.client.close.assert_awaited_once()
        assert daemon.client._token == "ghp_new_token"
        assert daemon.client._username == "newuser"
        assert daemon.client._repos == ["new/repo"]
        daemon.client.start.assert_awaited_once()

    async def test_close_called_before_update_and_start(self) -> None:
        daemon = Daemon(_make_config())
        new_config = _make_config()
        call_order: list[str] = []

        async def mock_close() -> None:
            call_order.append("close")

        async def mock_start() -> None:
            call_order.append("start")

        def mock_update(
            token: str,
            username: str,
            repos: list[str] | None = None,
            base_url: str = "https://api.github.com",
            max_retries: int = 3,
        ) -> None:
            call_order.append("update_config")

        daemon.client.close = mock_close  # type: ignore[method-assign]
        daemon.client.start = mock_start  # type: ignore[method-assign]
        daemon.client.update_config = mock_update  # type: ignore[method-assign]

        with patch("github_monitor.daemon.load_config", return_value=new_config):
            await daemon._reload_config()

        assert call_order == ["close", "update_config", "start"]

    async def test_reload_failure_is_caught(self) -> None:
        daemon = Daemon(_make_config())
        original_config = daemon.config

        with (
            patch("github_monitor.daemon.load_config", side_effect=FileNotFoundError("missing")),
            patch("github_monitor.daemon.logger") as mock_logger,
        ):
            await daemon._reload_config()

        mock_logger.exception.assert_called_once()
        # Config should remain unchanged on failure
        assert daemon.config is original_config

    async def test_reload_passes_config_path_to_load_config(self) -> None:
        custom_path = Path("/etc/github-monitor/config.toml")
        daemon = Daemon(_make_config(), config_path=custom_path)
        new_config = _make_config(github_token="ghp_reloaded")
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]

        with patch("github_monitor.daemon.load_config", return_value=new_config) as mock_load:
            await daemon._reload_config()

        mock_load.assert_called_once_with(custom_path)

    async def test_reload_passes_none_when_no_config_path(self) -> None:
        daemon = Daemon(_make_config())
        new_config = _make_config(github_token="ghp_reloaded")
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]

        with patch("github_monitor.daemon.load_config", return_value=new_config) as mock_load:
            await daemon._reload_config()

        mock_load.assert_called_once_with(None)


# ---------------------------------------------------------------------------
# Tests: reload signal handler
# ---------------------------------------------------------------------------


class TestHandleReload:
    """_handle_reload should schedule the async reload as a task."""

    async def test_schedules_reload_task(self) -> None:
        daemon = Daemon(_make_config())
        daemon._reload_config = AsyncMock()  # type: ignore[method-assign]

        daemon._handle_reload()

        # Give the event loop a chance to run the scheduled task
        await asyncio.sleep(0)

        daemon._reload_config.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: clean stop
# ---------------------------------------------------------------------------


class TestStop:
    """stop() should cleanly shut down all resources."""

    async def test_closes_client(self) -> None:
        daemon = Daemon(_make_config())
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]

        await daemon.stop()

        daemon.client.close.assert_awaited_once()

    async def test_disconnects_bus(self) -> None:
        daemon = Daemon(_make_config())
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.bus = MagicMock()

        await daemon.stop()

        daemon.bus.disconnect.assert_called_once()

    async def test_no_error_when_bus_is_none(self) -> None:
        daemon = Daemon(_make_config())
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.bus = None

        # Should not raise
        await daemon.stop()


# ---------------------------------------------------------------------------
# Tests: daemon start
# ---------------------------------------------------------------------------


class TestStart:
    """start() should initialise components and enter the poll loop."""

    async def test_calls_client_start(self) -> None:
        daemon = Daemon(_make_config())
        mock_bus = MagicMock()
        mock_interface = MagicMock()

        daemon.client.start = AsyncMock()  # type: ignore[method-assign]
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]

        with patch("github_monitor.daemon.setup_dbus", new_callable=AsyncMock) as mock_setup:
            mock_setup.return_value = (mock_bus, mock_interface)

            # Stop the daemon after one iteration
            original_poll_once = daemon._poll_once

            async def poll_and_stop() -> None:
                await original_poll_once()
                daemon._handle_shutdown()

            daemon._poll_once = poll_and_stop  # type: ignore[method-assign]
            await daemon.start()

        daemon.client.start.assert_awaited_once()

    async def test_sets_up_dbus(self) -> None:
        daemon = Daemon(_make_config())
        mock_bus = MagicMock()
        mock_interface = MagicMock()

        daemon.client.start = AsyncMock()  # type: ignore[method-assign]
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]

        with patch("github_monitor.daemon.setup_dbus", new_callable=AsyncMock) as mock_setup:
            mock_setup.return_value = (mock_bus, mock_interface)

            async def poll_and_stop() -> None:
                daemon._handle_shutdown()

            daemon._poll_once = poll_and_stop  # type: ignore[method-assign]
            await daemon.start()

        mock_setup.assert_awaited_once_with(daemon.store, daemon._poll_once)
        assert daemon.bus is mock_bus
        assert daemon.interface is mock_interface

    async def test_registers_signal_handlers(self) -> None:
        daemon = Daemon(_make_config())
        mock_bus = MagicMock()
        mock_interface = MagicMock()

        daemon.client.start = AsyncMock()  # type: ignore[method-assign]
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]

        with (
            patch("github_monitor.daemon.setup_dbus", new_callable=AsyncMock) as mock_setup,
            patch.object(asyncio.get_event_loop(), "add_signal_handler") as mock_add_handler,
        ):
            mock_setup.return_value = (mock_bus, mock_interface)

            async def poll_and_stop() -> None:
                daemon._handle_shutdown()

            daemon._poll_once = poll_and_stop  # type: ignore[method-assign]
            await daemon.start()

        # Check that SIGTERM, SIGINT, and SIGHUP handlers were registered
        handler_signals = [call.args[0] for call in mock_add_handler.call_args_list]
        assert signal.SIGTERM in handler_signals
        assert signal.SIGINT in handler_signals
        assert signal.SIGHUP in handler_signals

    async def test_sets_running_flag(self) -> None:
        daemon = Daemon(_make_config())
        mock_bus = MagicMock()
        mock_interface = MagicMock()
        running_during_poll = False

        daemon.client.start = AsyncMock()  # type: ignore[method-assign]
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]

        async def capture_and_stop() -> None:
            nonlocal running_during_poll
            running_during_poll = daemon._running
            daemon._handle_shutdown()

        with patch("github_monitor.daemon.setup_dbus", new_callable=AsyncMock) as mock_setup:
            mock_setup.return_value = (mock_bus, mock_interface)
            daemon._poll_once = capture_and_stop  # type: ignore[method-assign]
            await daemon.start()

        assert running_during_poll is True


# ---------------------------------------------------------------------------
# Tests: poll loop
# ---------------------------------------------------------------------------


class TestPollLoop:
    """_poll_loop should run _poll_once repeatedly until shutdown."""

    async def test_stops_on_shutdown_event(self) -> None:
        daemon = Daemon(_make_config(poll_interval=30))
        poll_count = 0

        async def counting_poll() -> None:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 2:
                daemon._handle_shutdown()

        daemon._running = True
        daemon._poll_once = counting_poll  # type: ignore[method-assign]

        await daemon._poll_loop()

        assert poll_count == 2
        assert daemon._running is False

    async def test_immediate_shutdown_wakes_from_sleep(self) -> None:
        """Shutdown event should interrupt the sleep immediately."""
        daemon = Daemon(_make_config(poll_interval=3600))
        poll_count = 0

        async def poll_then_schedule_shutdown() -> None:
            nonlocal poll_count
            poll_count += 1

            # Schedule shutdown after a tiny delay — should NOT wait 3600s
            async def delayed_shutdown() -> None:
                await asyncio.sleep(0.05)
                daemon._handle_shutdown()

            asyncio.get_running_loop().create_task(delayed_shutdown())

        daemon._running = True
        daemon._poll_once = poll_then_schedule_shutdown  # type: ignore[method-assign]

        # This should complete in ~0.05s, NOT 3600s
        await asyncio.wait_for(daemon._poll_loop(), timeout=2.0)

        assert poll_count == 1

    async def test_timeout_continues_to_next_poll(self) -> None:
        """TimeoutError from wait_for triggers continue → next poll cycle."""
        daemon = Daemon(_make_config(poll_interval=0))  # 0s interval → immediate timeout
        poll_count = 0

        async def counting_poll_then_stop() -> None:
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:
                daemon._handle_shutdown()

        daemon._running = True
        daemon._poll_once = counting_poll_then_stop  # type: ignore[method-assign]

        await asyncio.wait_for(daemon._poll_loop(), timeout=2.0)

        # Should have polled 3 times: first two via TimeoutError → continue,
        # third poll sets shutdown event → break
        assert poll_count == 3


# ---------------------------------------------------------------------------
# Tests: second poll notification behaviour
# ---------------------------------------------------------------------------


class TestSecondPollNotifications:
    """After the first poll, new PRs should trigger notifications."""

    async def test_second_poll_sends_notifications(self) -> None:
        daemon = Daemon(_make_config())
        daemon.interface = MagicMock()

        # First poll — notifications suppressed
        pr1 = _make_pr(1)
        daemon.client.fetch_all = AsyncMock(return_value=[pr1])  # type: ignore[method-assign]

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_not_awaited()

        # Second poll — new PR arrives, should notify
        pr2 = _make_pr(2)
        daemon.client.fetch_all = AsyncMock(return_value=[pr1, pr2])  # type: ignore[method-assign]

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_awaited_once()
            notified_prs = mock_notify.call_args[0][0]
            assert len(notified_prs) == 1
            assert notified_prs[0].number == 2


# ---------------------------------------------------------------------------
# Tests: notifications_enabled config
# ---------------------------------------------------------------------------


class TestNotificationsEnabled:
    """notifications_enabled config controls whether notifications fire."""

    async def test_disabled_suppresses_all_notifications(self) -> None:
        daemon = Daemon(_make_config(notifications_enabled=False))
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_not_awaited()

    async def test_enabled_sends_notifications(self) -> None:
        daemon = Daemon(_make_config(notifications_enabled=True))
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: notify_on_first_poll config
# ---------------------------------------------------------------------------


class TestNotifyOnFirstPoll:
    """notify_on_first_poll config controls first-poll notification behavior."""

    async def test_first_poll_notifies_when_enabled(self) -> None:
        daemon = Daemon(_make_config(notify_on_first_poll=True))
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        assert daemon._first_poll is True

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_awaited_once()

    async def test_first_poll_suppressed_when_disabled(self) -> None:
        daemon = Daemon(_make_config(notify_on_first_poll=False))
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        assert daemon._first_poll is True

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: notification_threshold and notification_urgency passthrough
# ---------------------------------------------------------------------------


class TestNotificationConfigPassthrough:
    """Config values for threshold and urgency are passed to notify_new_prs."""

    async def test_custom_threshold_and_urgency_passed(self) -> None:
        daemon = Daemon(_make_config(notification_threshold=10, notification_urgency="critical"))
        prs = [_make_pr(1)]
        daemon.client.fetch_all = AsyncMock(return_value=prs)  # type: ignore[method-assign]
        daemon.interface = MagicMock()
        daemon._first_poll = False

        with patch("github_monitor.daemon.notify_new_prs", new_callable=AsyncMock) as mock_notify:
            await daemon._poll_once()
            mock_notify.assert_awaited_once_with(
                prs,
                threshold=10,
                urgency="critical",
            )


# ---------------------------------------------------------------------------
# Tests: dbus_enabled config
# ---------------------------------------------------------------------------


class TestDbusEnabled:
    """dbus_enabled config controls whether D-Bus is registered on start."""

    async def test_dbus_disabled_skips_setup(self) -> None:
        daemon = Daemon(_make_config(dbus_enabled=False))
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.fetch_all = AsyncMock(return_value=[])  # type: ignore[method-assign]

        with patch("github_monitor.daemon.setup_dbus", new_callable=AsyncMock) as mock_setup:

            async def poll_and_stop() -> None:
                daemon._handle_shutdown()

            daemon._poll_once = poll_and_stop  # type: ignore[method-assign]
            await daemon.start()

            mock_setup.assert_not_awaited()
            assert daemon.bus is None
            assert daemon.interface is None

    async def test_dbus_enabled_calls_setup(self) -> None:
        daemon = Daemon(_make_config(dbus_enabled=True))
        mock_bus = MagicMock()
        mock_interface = MagicMock()
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]

        with patch("github_monitor.daemon.setup_dbus", new_callable=AsyncMock) as mock_setup:
            mock_setup.return_value = (mock_bus, mock_interface)

            async def poll_and_stop() -> None:
                daemon._handle_shutdown()

            daemon._poll_once = poll_and_stop  # type: ignore[method-assign]
            await daemon.start()

            mock_setup.assert_awaited_once()
            assert daemon.bus is mock_bus
            assert daemon.interface is mock_interface


# ---------------------------------------------------------------------------
# Tests: log level on config reload
# ---------------------------------------------------------------------------


class TestReloadLogLevel:
    """_reload_config should apply the new log_level from reloaded config."""

    async def test_reload_applies_log_level(self) -> None:
        daemon = Daemon(_make_config(log_level="info"))
        new_config = _make_config(log_level="debug")
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]

        with patch("github_monitor.daemon.load_config", return_value=new_config):
            await daemon._reload_config()

        assert logging.getLogger().level == logging.DEBUG

    async def test_reload_applies_warning_level(self) -> None:
        daemon = Daemon(_make_config(log_level="debug"))
        new_config = _make_config(log_level="warning")
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]

        with patch("github_monitor.daemon.load_config", return_value=new_config):
            await daemon._reload_config()

        assert logging.getLogger().level == logging.WARNING


# ---------------------------------------------------------------------------
# Tests: client receives base_url and max_retries
# ---------------------------------------------------------------------------


class TestClientConfigPassthrough:
    """Daemon passes github_base_url and max_retries to GitHubClient."""

    def test_client_receives_base_url_and_max_retries(self) -> None:
        config = _make_config(
            github_base_url="https://gh.corp.example.com/api/v3",
            max_retries=5,
        )
        daemon = Daemon(config)
        assert daemon.client._base_url == "https://gh.corp.example.com/api/v3"
        assert daemon.client._max_retries == 5

    async def test_reload_passes_base_url_and_max_retries(self) -> None:
        daemon = Daemon(_make_config())
        new_config = _make_config(
            github_base_url="https://gh.new.example.com",
            max_retries=7,
        )
        daemon.client.close = AsyncMock()  # type: ignore[method-assign]
        daemon.client.start = AsyncMock()  # type: ignore[method-assign]

        with patch("github_monitor.daemon.load_config", return_value=new_config):
            await daemon._reload_config()

        assert daemon.client._base_url == "https://gh.new.example.com"
        assert daemon.client._max_retries == 7
